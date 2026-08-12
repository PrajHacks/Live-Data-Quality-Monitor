"""Fetch live product data from Open Food Facts and save a flat CSV extract.

The script uses the structured v2 search API because it is the current official
search endpoint for filter-based queries. To stay under the anonymous per-query
result ceiling, we split the pull across a few beverage batches filtered by
country and dedupe by barcode.
"""

from __future__ import annotations

import shutil
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_URL = "https://world.openfoodfacts.net/api/v2/search"
USER_AGENT = "live-data-quality-monitor/0.1 (local development)"
DEFAULT_CATEGORY = "beverages"
TARGET_ROWS = 2000
PAGE_SIZE = 100
REQUEST_TIMEOUT_SECONDS = 30
REQUEST_DELAY_SECONDS = 7
MAX_PAGES_PER_QUERY = 10
COUNTRY_FILTERS = [
    "united-states",
    "france",
    "united-kingdom",
    "germany",
    "canada",
]

OUTPUT_COLUMNS = [
    "code",
    "product_name",
    "brands",
    "categories",
    "countries",
    "nutrition_grade_fr",
    "energy_100g",
    "sugars_100g",
    "fat_100g",
    "salt_100g",
    "ingredients_text",
    "last_modified_t",
]


def is_missing(value: Any) -> bool:
    """Return True when a value should be treated as missing/null."""

    if value is None or value is pd.NA:
        return True

    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def clean_text(value: Any) -> str | None:
    """Normalize API text fields so blank values become proper nulls."""

    if is_missing(value):
        return None

    text = str(value).strip()
    return text or None


def coerce_float(value: Any) -> float | None:
    """Convert numeric-looking values to floats while preserving missing data."""

    if is_missing(value):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_timestamp(value: Any) -> str | None:
    """Convert Open Food Facts epoch timestamps into a readable UTC string."""

    if is_missing(value):
        return None

    try:
        timestamp = int(float(value))
    except (TypeError, ValueError):
        return None

    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def build_search_params(page: int, page_size: int, country: str | None = None) -> dict[str, Any]:
    """Build the structured v2 search query.

    We keep the payload small by requesting only the fields needed for the flat
    output table, and we filter to one category so the sample stays focused.
    Results are sorted by last-modified time so the newest products appear first.
    The live API may cap requested page sizes, so the fetch loop keeps paging
    until the target row count is reached.
    """

    params: dict[str, Any] = {
        "categories_tags_en": DEFAULT_CATEGORY,
        "sort_by": "last_modified_t",
        "page": page,
        "page_size": page_size,
        "fields": ",".join(
            [
                "code",
                "product_name",
                "brands",
                "categories",
                "countries",
                "nutrition_grade_fr",
                "nutriscore_grade",
                "ingredients_text",
                "last_modified_t",
                "nutriments",
            ]
        ),
    }

    if country:
        params["countries_tags_en"] = country

    return params


def _country_sequence(seed: int | None = None) -> list[str]:
    """Return a fresh country order so consecutive runs sample different rows."""

    rng = random.Random(seed if seed is not None else time.time_ns())
    countries = list(COUNTRY_FILTERS)
    rng.shuffle(countries)
    return countries


def request_json(session: requests.Session, params: dict[str, Any]) -> dict[str, Any]:
    """Call the API with a single retry for timeouts or request failures."""

    last_error: Exception | None = None

    for attempt in range(1, 3):
        try:
            response = session.get(
                API_URL,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt == 1:
                print(
                    "Open Food Facts request failed on attempt 1/2: "
                    f"{exc}. Retrying once..."
                )
                time.sleep(2)

    raise RuntimeError(
        "Failed to fetch Open Food Facts data after 2 attempts"
    ) from last_error


def fetch_products_for_country(
    session: requests.Session,
    country: str,
    target_rows: int,
    page_size: int = PAGE_SIZE,
) -> list[dict[str, Any]]:
    """Fetch one country-filtered beverage batch up to the per-query ceiling."""

    rows: list[dict[str, Any]] = []
    query_cap = min(target_rows, PAGE_SIZE * MAX_PAGES_PER_QUERY)

    for page in range(1, MAX_PAGES_PER_QUERY + 1):
        if len(rows) >= query_cap:
            break

        current_page_size = min(page_size, query_cap - len(rows))
        params = build_search_params(
            page=page,
            page_size=current_page_size,
            country=country,
        )

        try:
            payload = request_json(session, params)
        except RuntimeError as exc:
            print(f"Stopping country batch {country!r} after page {page}: {exc}")
            break

        products = payload.get("products", [])
        if not products:
            break

        rows.extend(products)
        print(
            f"Fetched {country} page {page}: {len(products)} products "
            f"(running total {len(rows)})"
        )

        if len(rows) < query_cap:
            time.sleep(REQUEST_DELAY_SECONDS)

    return rows


def fetch_products(target_rows: int = TARGET_ROWS, seed: int | None = None) -> list[dict[str, Any]]:
    """Fetch multiple country batches until we have the requested unique rows."""

    normalized_rows: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    country_filters = _country_sequence(seed)

    with requests.Session() as session:
        session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            }
        )

        for country in country_filters:
            if len(normalized_rows) >= target_rows:
                break

            print(f"\nFetching beverage batch for country filter: {country}")
            remaining_target = target_rows - len(normalized_rows)
            country_products = fetch_products_for_country(
                session=session,
                country=country,
                target_rows=remaining_target,
            )

            for product in country_products:
                row = extract_product_row(product)
                code = row["code"]

                if code and code in seen_codes:
                    continue
                if code:
                    seen_codes.add(code)

                normalized_rows.append(row)
                if len(normalized_rows) >= target_rows:
                    break

    return normalized_rows


def extract_product_row(product: dict[str, Any]) -> dict[str, Any]:
    """Flatten one Open Food Facts product into the target table schema."""

    # The nutriments object carries the per-100g nutrition values we need.
    nutriments = product.get("nutriments") or {}

    # Nutri-Score is usually exposed as nutrition_grade_fr, but we fall back to
    # the newer nutriscore_grade field if the legacy field is absent.
    nutrition_grade = clean_text(product.get("nutrition_grade_fr"))
    if nutrition_grade is None:
        nutrition_grade = clean_text(product.get("nutriscore_grade"))

    return {
        "code": clean_text(product.get("code")),
        "product_name": clean_text(product.get("product_name")),
        "brands": clean_text(product.get("brands")),
        "categories": clean_text(product.get("categories")),
        "countries": clean_text(product.get("countries")),
        "nutrition_grade_fr": nutrition_grade,
        "energy_100g": coerce_float(nutriments.get("energy-kcal_100g")),
        "sugars_100g": coerce_float(nutriments.get("sugars_100g")),
        "fat_100g": coerce_float(nutriments.get("fat_100g")),
        "salt_100g": coerce_float(nutriments.get("salt_100g")),
        "ingredients_text": clean_text(product.get("ingredients_text")),
        "last_modified_t": format_timestamp(product.get("last_modified_t")),
    }


def build_dataframe(products: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert normalized product rows into a flat Pandas DataFrame."""

    return pd.DataFrame(products, columns=OUTPUT_COLUMNS)


def save_outputs(df: pd.DataFrame) -> tuple[Path, Path]:
    """Write both a timestamped CSV and a convenience latest copy."""

    output_dir = PROJECT_ROOT / "data" / "incoming"
    output_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
    timestamped_path = output_dir / f"products_{stamp}.csv"
    latest_path = output_dir / "products_latest.csv"

    df.to_csv(timestamped_path, index=False)
    shutil.copyfile(timestamped_path, latest_path)

    return timestamped_path, latest_path


def print_quality_summary(df: pd.DataFrame) -> None:
    """Print a lightweight data-quality snapshot for the extracted table."""

    print("\nData quality summary")
    print(f"Total rows fetched: {len(df)}")

    missing_pct = df.isna().mean().mul(100).round(1)
    missing_count = df.isna().sum()

    for column in df.columns:
        print(
            f"- {column}: {missing_pct[column]:.1f}% missing "
            f"({int(missing_count[column])} rows)"
        )


def main() -> int:
    try:
        rows = fetch_products()
    except RuntimeError as exc:
        print(f"Error fetching Open Food Facts data: {exc}")
        return 1

    if not rows:
        print("No products were returned by the Open Food Facts API.")
        return 1

    df = build_dataframe(rows)
    timestamped_path, latest_path = save_outputs(df)

    print(f"\nSaved timestamped extract to: {timestamped_path}")
    print(f"Saved latest extract to: {latest_path}")

    if len(df) < TARGET_ROWS:
        print(
            f"Warning: the selected country batches only returned {len(df)} "
            f"products, so the output contains fewer than {TARGET_ROWS} rows."
        )

    print_quality_summary(df)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
