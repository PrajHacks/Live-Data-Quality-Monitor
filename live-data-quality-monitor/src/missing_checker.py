"""Missing-value checks for the validation pipeline."""

from __future__ import annotations

from typing import Any

import pandas as pd


Issue = dict[str, Any]


def _missing_mask(series: pd.Series) -> pd.Series:
    """Treat nulls and blank strings as missing values."""

    text = series.astype("string").str.strip()
    return series.isna() | text.eq("")


def _missing_severity(missing_pct: float) -> str:
    """Classify missingness for generic schemas."""

    if missing_pct > 70:
        return "Critical"
    if missing_pct > 30:
        return "Warning"
    return "Info"


def _check_missing_structured(df: pd.DataFrame, rules: dict[str, Any]) -> list[Issue]:
    """Return missing-value issues for the built-in Open Food Facts schema."""

    issues: list[Issue] = []
    required_columns = rules.get("required_columns", [])
    critical_columns = set(rules.get("critical_columns", []))
    total_rows = len(df)

    for column in required_columns:
        if column not in df.columns:
            missing_count = total_rows
        else:
            missing_count = int(_missing_mask(df[column]).sum())

        if missing_count == 0:
            continue

        missing_pct = (missing_count / total_rows * 100) if total_rows else 0.0
        severity = "Critical" if column in critical_columns else "Warning"

        issues.append(
            {
                "column": column,
                "issue_type": "missing_values",
                "count": missing_count,
                "severity": severity,
                "details": f"{missing_count} missing rows out of {total_rows} "
                f"({missing_pct:.1f}%).",
            }
        )

    return issues


def _check_missing_generic(df: pd.DataFrame) -> list[Issue]:
    """Return missing-value issues for any arbitrary DataFrame."""

    issues: list[Issue] = []
    total_rows = len(df)

    for column in df.columns:
        missing_count = int(_missing_mask(df[column]).sum())
        if missing_count == 0:
            continue

        missing_pct = (missing_count / total_rows * 100) if total_rows else 0.0
        issues.append(
            {
                "column": column,
                "issue_type": "missing_values",
                "count": missing_count,
                "severity": _missing_severity(missing_pct),
                "details": f"{missing_count} missing rows out of {total_rows} "
                f"({missing_pct:.1f}%).",
            }
        )

    return issues


def check_missing_values(df: pd.DataFrame, rules: dict[str, Any]) -> list[Issue]:
    """Return missing-value issues for the active validation mode."""

    if rules.get("_analysis_mode") == "generic":
        return _check_missing_generic(df)

    # If a caller has not populated runtime metadata, preserve the original behavior.
    if "_analysis_mode" not in rules:
        return _check_missing_structured(df, rules)

    return _check_missing_structured(df, rules)
