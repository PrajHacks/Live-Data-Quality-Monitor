"""Hard range checks for numeric product columns."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.schema_detector import detect_schema


Issue = dict[str, Any]


def _check_ranges_structured(df: pd.DataFrame, rules: dict[str, Any]) -> list[Issue]:
    """Return fixed min/max range violations for the OFF nutrition columns."""

    issues: list[Issue] = []
    ranges = rules.get("ranges", {})

    for column, bounds in ranges.items():
        if column not in df.columns:
            continue

        minimum = bounds.get("min")
        maximum = bounds.get("max")
        if minimum is None or maximum is None:
            continue

        raw_series = df[column]
        numeric = pd.to_numeric(raw_series, errors="coerce")
        present_mask = raw_series.astype("string").str.strip().ne("")
        present_mask = present_mask & raw_series.notna()

        invalid_mask = present_mask & numeric.isna()
        out_of_range_mask = numeric.notna() & ((numeric < minimum) | (numeric > maximum))

        invalid_count = int(invalid_mask.sum())
        out_of_range_count = int(out_of_range_mask.sum())
        total_count = invalid_count + out_of_range_count

        if total_count == 0:
            continue

        detail_parts: list[str] = []
        if invalid_count:
            detail_parts.append(f"{invalid_count} non-numeric values")
        if out_of_range_count:
            detail_parts.append(
                f"{out_of_range_count} values outside {minimum} to {maximum}"
            )

        issues.append(
            {
                "column": column,
                "issue_type": "out_of_range",
                "count": total_count,
                "severity": "Warning",
                "details": "; ".join(detail_parts) + ".",
            }
        )

    return issues


def _check_ranges_generic(df: pd.DataFrame, rules: dict[str, Any]) -> list[Issue]:
    """Return robust IQR-based numeric range issues for arbitrary data."""

    issues: list[Issue] = []
    schema = rules.get("_schema_detection") or detect_schema(df)
    column_types = schema.get("column_types", {})

    for column, column_type in column_types.items():
        if column_type != "numeric" or column not in df.columns:
            continue

        raw_series = df[column]
        numeric = pd.to_numeric(raw_series, errors="coerce")
        present_mask = raw_series.astype("string").str.strip().ne("")
        present_mask = present_mask & raw_series.notna()

        invalid_mask = present_mask & numeric.isna()
        invalid_count = int(invalid_mask.sum())

        valid_values = numeric[numeric.notna()]
        outlier_count = 0
        lower_bound = upper_bound = None
        if len(valid_values) >= 4:
            q1 = valid_values.quantile(0.25)
            q3 = valid_values.quantile(0.75)
            iqr = q3 - q1

            if pd.notna(iqr) and iqr > 0:
                lower_bound = q1 - 3.0 * iqr
                upper_bound = q3 + 3.0 * iqr
                outlier_mask = valid_values.lt(lower_bound) | valid_values.gt(upper_bound)
                outlier_count = int(outlier_mask.sum())

        total_count = invalid_count + outlier_count
        if total_count == 0:
            continue

        detail_parts: list[str] = []
        if invalid_count:
            detail_parts.append(f"{invalid_count} non-numeric values")
        if outlier_count:
            if lower_bound is not None and upper_bound is not None:
                detail_parts.append(
                    f"{outlier_count} values outside robust range {lower_bound:.2f} to {upper_bound:.2f}"
                )
            else:
                detail_parts.append(f"{outlier_count} statistical outliers")

        issues.append(
            {
                "column": column,
                "issue_type": "out_of_range",
                "count": total_count,
                "severity": "Warning",
                "details": "; ".join(detail_parts) + ".",
            }
        )

    return issues


def check_ranges(df: pd.DataFrame, rules: dict[str, Any]) -> list[Issue]:
    """Return range issues for both structured and generic validation modes."""

    if rules.get("_analysis_mode") == "generic":
        return _check_ranges_generic(df, rules)

    return _check_ranges_structured(df, rules)
