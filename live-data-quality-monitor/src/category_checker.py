"""Category/value-domain checks for the Nutri-Score field."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from src.schema_detector import detect_schema


Issue = dict[str, Any]


def _check_nutrition_grades_structured(df: pd.DataFrame, rules: dict[str, Any]) -> list[Issue]:
    """Return unexpected Nutri-Score values as informational issues."""

    if "nutrition_grade_fr" not in df.columns:
        return []

    allowed = {
        str(value).strip().lower()
        for value in rules.get("allowed_nutrition_grades", [])
        if str(value).strip()
    }

    normalized = df["nutrition_grade_fr"].astype("string").str.strip().str.lower()
    present_mask = normalized.notna() & normalized.ne("")
    unexpected_mask = present_mask & ~normalized.isin(allowed)
    unexpected_count = int(unexpected_mask.sum())

    if unexpected_count == 0:
        return []

    unexpected_values = Counter(normalized[unexpected_mask].tolist())
    examples = ", ".join(
        f"{value} ({count})" for value, count in unexpected_values.most_common(5)
    )
    if len(unexpected_values) > 5:
        examples += ", ..."

    return [
        {
            "column": "nutrition_grade_fr",
            "issue_type": "unexpected_values",
            "count": unexpected_count,
            "severity": "Info",
            "details": "Unexpected nutrition grades: " + examples + ".",
        }
    ]


def _check_categorical_rare_values(df: pd.DataFrame, rules: dict[str, Any]) -> list[Issue]:
    """Return rare categorical values as generic consistency hints."""

    issues: list[Issue] = []
    schema = rules.get("_schema_detection") or detect_schema(df)
    column_types = schema.get("column_types", {})
    total_rows = len(df)

    if total_rows == 0:
        return issues

    for column, column_type in column_types.items():
        if column_type != "categorical" or column not in df.columns:
            continue

        normalized = df[column].astype("string").str.strip()
        present_mask = normalized.notna() & normalized.ne("")
        values = normalized[present_mask]
        if values.empty:
            continue

        value_counts = values.value_counts(dropna=False)
        rare_values = value_counts[value_counts / total_rows < 0.005]

        if rare_values.empty:
            continue

        examples = ", ".join(
            f"{value} ({count})" for value, count in rare_values.head(5).items()
        )
        if len(rare_values) > 5:
            examples += ", ..."

        issues.append(
            {
                "column": column,
                "issue_type": "rare_values",
                "count": int(rare_values.sum()),
                "severity": "Warning",
                "details": "Rare categorical values that may be typos or inconsistent labels: "
                + examples
                + ".",
            }
        )

    return issues


def check_nutrition_grades(df: pd.DataFrame, rules: dict[str, Any]) -> list[Issue]:
    """Return category-related issues for both structured and generic modes."""

    if rules.get("_analysis_mode") == "generic":
        return _check_categorical_rare_values(df, rules)

    return _check_nutrition_grades_structured(df, rules)
