"""Duplicate-row and duplicate-barcode checks."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.schema_detector import detect_schema


Issue = dict[str, Any]


def _clean_string_series(series: pd.Series) -> pd.Series:
    """Normalize text-like values for duplicate detection."""

    return series.astype("string").str.strip()


def _check_duplicates_structured(df: pd.DataFrame) -> list[Issue]:
    """Return duplicate-row and duplicate-barcode issues for OFF data."""

    issues: list[Issue] = []

    duplicate_row_mask = df.duplicated(keep="first")
    duplicate_row_count = int(duplicate_row_mask.sum())
    if duplicate_row_count:
        duplicate_row_groups = int(df[df.duplicated(keep=False)].drop_duplicates().shape[0])
        issues.append(
            {
                "column": "__row__",
                "issue_type": "duplicate_rows",
                "count": duplicate_row_count,
                "severity": "Warning",
                "details": f"{duplicate_row_count} duplicate rows across "
                f"{duplicate_row_groups} repeated row patterns.",
            }
        )

    if "code" not in df.columns:
        return issues

    codes = _clean_string_series(df["code"])
    valid_codes = codes[codes.notna() & codes.ne("")]
    duplicate_code_mask = valid_codes.duplicated(keep="first")
    duplicate_code_count = int(duplicate_code_mask.sum())

    if duplicate_code_count:
        duplicate_code_values = int(valid_codes[valid_codes.duplicated(keep=False)].nunique())
        issues.append(
            {
                "column": "code",
                "issue_type": "duplicate_barcodes",
                "count": duplicate_code_count,
                "severity": "Critical",
                "details": f"{duplicate_code_count} duplicate barcode rows across "
                f"{duplicate_code_values} repeated barcodes.",
            }
        )

    return issues


def _check_duplicates_generic(df: pd.DataFrame, rules: dict[str, Any]) -> list[Issue]:
    """Return duplicate-row and identifier duplicate issues for any schema."""

    issues: list[Issue] = []

    duplicate_row_mask = df.duplicated(keep="first")
    duplicate_row_count = int(duplicate_row_mask.sum())
    if duplicate_row_count:
        duplicate_row_groups = int(df[df.duplicated(keep=False)].drop_duplicates().shape[0])
        issues.append(
            {
                "column": "__row__",
                "issue_type": "duplicate_rows",
                "count": duplicate_row_count,
                "severity": "Warning",
                "details": f"{duplicate_row_count} duplicate rows across "
                f"{duplicate_row_groups} repeated row patterns.",
            }
        )

    schema = rules.get("_schema_detection") or detect_schema(df)
    column_types = schema.get("column_types", {})
    identifier_columns = [
        column
        for column, column_type in column_types.items()
        if column_type == "identifier"
        and column in df.columns
    ]

    for column in identifier_columns:
        values = _clean_string_series(df[column])
        valid_values = values[values.notna() & values.ne("")]
        duplicate_mask = valid_values.duplicated(keep="first")
        duplicate_count = int(duplicate_mask.sum())
        if duplicate_count == 0:
            continue

        duplicate_value_count = int(valid_values[valid_values.duplicated(keep=False)].nunique())
        issues.append(
            {
                "column": column,
                "issue_type": "duplicate_identifiers",
                "count": duplicate_count,
                "severity": "Critical",
                "details": f"{duplicate_count} duplicate rows across "
                f"{duplicate_value_count} repeated values in {column!r}.",
            }
        )

    return issues


def check_duplicates(df: pd.DataFrame, rules: dict[str, Any]) -> list[Issue]:
    """Return duplicate-row issues in both structured and generic modes."""

    if rules.get("_analysis_mode") == "generic":
        return _check_duplicates_generic(df, rules)

    return _check_duplicates_structured(df)
