"""IQR-based outlier checks for nutrition values."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.schema_detector import detect_schema


Issue = dict[str, Any]


def _check_outliers_structured(df: pd.DataFrame, rules: dict[str, Any]) -> list[Issue]:
    """Detect statistical outliers within the valid hard range for key metrics."""

    issues: list[Issue] = []
    ranges = rules.get("ranges", {})

    for column in ["energy_100g", "sugars_100g", "fat_100g"]:
        if column not in df.columns or column not in ranges:
            continue

        bounds = ranges[column]
        minimum = bounds.get("min")
        maximum = bounds.get("max")
        if minimum is None or maximum is None:
            continue

        numeric = pd.to_numeric(df[column], errors="coerce")
        valid_mask = numeric.notna() & numeric.between(minimum, maximum, inclusive="both")
        valid_values = numeric[valid_mask]

        if len(valid_values) < 4:
            continue

        q1 = valid_values.quantile(0.25)
        q3 = valid_values.quantile(0.75)
        iqr = q3 - q1

        if pd.isna(iqr) or iqr <= 0:
            continue

        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        outlier_mask = valid_values.lt(lower_bound) | valid_values.gt(upper_bound)
        outlier_count = int(outlier_mask.sum())

        if outlier_count == 0:
            continue

        issues.append(
            {
                "column": column,
                "issue_type": "iqr_outliers",
                "count": outlier_count,
                "severity": "Warning",
                "details": (
                    f"{outlier_count} values outside IQR bounds "
                    f"{lower_bound:.2f} to {upper_bound:.2f} "
                    f"within valid range {minimum} to {maximum}."
                ),
            }
        )

    return issues


def _check_outliers_generic(df: pd.DataFrame, rules: dict[str, Any]) -> list[Issue]:
    """Detect IQR outliers for every numeric column in an unknown schema."""

    issues: list[Issue] = []
    schema = rules.get("_schema_detection") or detect_schema(df)
    column_types = schema.get("column_types", {})

    for column, column_type in column_types.items():
        if column_type != "numeric" or column not in df.columns:
            continue

        numeric = pd.to_numeric(df[column], errors="coerce")
        valid_values = numeric[numeric.notna()]

        if len(valid_values) < 4:
            continue

        q1 = valid_values.quantile(0.25)
        q3 = valid_values.quantile(0.75)
        iqr = q3 - q1

        if pd.isna(iqr) or iqr <= 0:
            continue

        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        outlier_mask = valid_values.lt(lower_bound) | valid_values.gt(upper_bound)
        outlier_count = int(outlier_mask.sum())

        if outlier_count == 0:
            continue

        issues.append(
            {
                "column": column,
                "issue_type": "iqr_outliers",
                "count": outlier_count,
                "severity": "Warning",
                "details": (
                    f"{outlier_count} values outside IQR bounds "
                    f"{lower_bound:.2f} to {upper_bound:.2f}."
                ),
            }
        )

    return issues


def check_outliers(df: pd.DataFrame, rules: dict[str, Any]) -> list[Issue]:
    """Detect statistical outliers for both structured and generic modes."""

    if rules.get("_analysis_mode") == "generic":
        return _check_outliers_generic(df, rules)

    return _check_outliers_structured(df, rules)
