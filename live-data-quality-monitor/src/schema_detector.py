"""Infer lightweight schema information for arbitrary CSV inputs."""

from __future__ import annotations

from typing import Any

import pandas as pd


OPEN_FOOD_FACTS_SCHEMA_COLUMNS = (
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
)

STRUCTURED_MATCH_THRESHOLD = 0.6


def _normalize_series(series: pd.Series) -> pd.Series:
    """Normalize text-like values and preserve numeric/date dtypes."""

    if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
        return series

    normalized = series.astype("string").str.strip()
    return normalized.replace("", pd.NA)


def _text_metrics(series: pd.Series) -> tuple[pd.Series, int, int, float, float, float]:
    """Return a normalized series together with basic cardinality metrics."""

    normalized = _normalize_series(series)
    non_missing = normalized.dropna()
    non_missing_count = int(non_missing.shape[0])
    unique_count = int(non_missing.nunique(dropna=True))
    unique_ratio = (unique_count / non_missing_count) if non_missing_count else 0.0
    lengths = non_missing.astype("string").str.len().mean() if non_missing_count else None
    avg_length = float(lengths) if lengths is not None and pd.notna(lengths) else 0.0
    spaces = (
        non_missing.astype("string").str.contains(r"\s", regex=True).mean()
        if non_missing_count
        else None
    )
    space_ratio = float(spaces) if spaces is not None and pd.notna(spaces) else 0.0
    return normalized, non_missing_count, unique_count, unique_ratio, avg_length, space_ratio


def _identifier_likelihood(column_name: str, unique_ratio: float, unique_count: int, avg_length: float, space_ratio: float) -> bool:
    """Heuristically decide whether a column behaves like an identifier."""

    lowered = column_name.lower()
    name_hint = any(
        token in lowered
        for token in (
            "id",
            "key",
            "code",
            "uuid",
            "identifier",
            "barcode",
            "sku",
            "record",
        )
    )

    if unique_count == 0:
        return False

    if unique_ratio >= 0.95 and avg_length <= 32 and space_ratio < 0.15:
        return True

    if name_hint and unique_ratio >= 0.7 and unique_count > 20 and space_ratio < 0.3:
        return True

    return False


def _should_try_date_detection(column_name: str, normalized: pd.Series) -> bool:
    """Avoid expensive date parsing unless the column looks date-like."""

    lowered = column_name.lower()
    if any(token in lowered for token in ("date", "time", "timestamp", "created", "modified", "updated")):
        return True

    sample = normalized.dropna().astype("string").head(25)
    if sample.empty:
        return False

    iso_ratio = float(sample.str.match(r"^\d{4}-\d{2}-\d{2}").mean() or 0.0)
    slash_ratio = float(sample.str.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$").mean() or 0.0)
    datetime_ratio = float(sample.str.contains(r"\d{2}:\d{2}", regex=True).mean() or 0.0)
    return iso_ratio >= 0.4 or slash_ratio >= 0.4 or datetime_ratio >= 0.4


def _classify_column(column_name: str, series: pd.Series) -> tuple[str, dict[str, Any]]:
    """Classify a single column using a few broad, explainable heuristics."""

    normalized, non_missing_count, unique_count, unique_ratio, avg_length, space_ratio = _text_metrics(series)

    numeric_series = pd.to_numeric(normalized, errors="coerce")
    numeric_count = int(numeric_series.notna().sum())
    numeric_ratio = (numeric_count / non_missing_count) if non_missing_count else 0.0
    date_ratio = 0.0

    if _identifier_likelihood(column_name, unique_ratio, unique_count, avg_length, space_ratio):
        column_type = "identifier"
    else:
        if _should_try_date_detection(column_name, normalized):
            date_series = pd.to_datetime(normalized, errors="coerce")
            date_count = int(date_series.notna().sum())
            date_ratio = (date_count / non_missing_count) if non_missing_count else 0.0

        if pd.api.types.is_numeric_dtype(series) or numeric_ratio >= 0.9:
            column_type = "numeric"
        elif date_ratio >= 0.8 and date_ratio >= numeric_ratio:
            column_type = "date"
        elif unique_count <= 20 and (avg_length <= 32 or unique_ratio <= 0.2):
            column_type = "categorical"
        else:
            column_type = "text"

    stats = {
        "non_missing_count": non_missing_count,
        "unique_count": unique_count,
        "unique_ratio": unique_ratio,
        "numeric_parse_ratio": numeric_ratio,
        "date_parse_ratio": date_ratio,
        "avg_length": avg_length,
        "space_ratio": space_ratio,
    }

    return column_type, stats


def detect_schema(df: pd.DataFrame) -> dict[str, Any]:
    """Infer a broad schema profile for any DataFrame."""

    column_types: dict[str, str] = {}
    column_stats: dict[str, dict[str, Any]] = {}
    summary = {
        "total_columns": len(df.columns),
        "numeric_count": 0,
        "categorical_count": 0,
        "text_count": 0,
        "identifier_count": 0,
        "date_count": 0,
    }

    for column in df.columns:
        column_type, stats = _classify_column(str(column), df[column])
        column_types[column] = column_type
        column_stats[column] = stats
        summary[f"{column_type}_count"] += 1

    return {
        "column_types": column_types,
        "column_stats": column_stats,
        "summary": summary,
    }


def is_open_food_facts_schema(df: pd.DataFrame, rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return whether a DataFrame closely matches the built-in product schema."""

    expected_columns = tuple((rules or {}).get("structured_schema_columns", OPEN_FOOD_FACTS_SCHEMA_COLUMNS))
    expected_set = set(expected_columns)
    actual_set = set(df.columns)
    matched_columns = sorted(expected_set & actual_set)
    match_ratio = (len(matched_columns) / len(expected_set)) if expected_set else 0.0
    critical_columns = set((rules or {}).get("critical_columns", []))
    required_match = critical_columns.issubset(actual_set) if critical_columns else True
    is_match = required_match and match_ratio >= STRUCTURED_MATCH_THRESHOLD

    return {
        "is_match": is_match,
        "match_ratio": match_ratio,
        "expected_columns": list(expected_columns),
        "matched_columns": matched_columns,
    }
