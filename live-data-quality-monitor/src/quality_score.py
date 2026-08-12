"""Calculate a weighted data-quality score from validation issues."""

from __future__ import annotations

from typing import Any


Issue = dict[str, Any]

DEFAULT_SCORE_BANDS = {
    "Excellent": 90.0,
    "Warning": 75.0,
    "Failed": 0.0,
}


def _sum_issue_counts(issues: list[Issue], issue_types: set[str]) -> int:
    """Sum issue counts for the requested issue types."""

    return sum(
        int(issue.get("count", 0))
        for issue in issues
        if issue.get("issue_type") in issue_types
    )


def _runtime_count(rules: dict[str, Any] | None, key: str, fallback: int = 0) -> int:
    """Read an integer runtime count from the rules payload."""

    try:
        return int((rules or {}).get(key, fallback))
    except (TypeError, ValueError):
        return fallback


def _score_from_penalty(total_penalty: int, denominator: int) -> float:
    """Convert a penalty count into a 0-100 score."""

    if denominator <= 0:
        return 0.0

    score = 100.0 - (total_penalty / denominator * 100.0)
    return max(0.0, min(100.0, score))


def _normalize_score_bands(rules: dict[str, Any] | None) -> dict[str, float]:
    """Return score-band thresholds from rules, falling back to defaults."""

    raw_bands = (rules or {}).get("score_bands", DEFAULT_SCORE_BANDS)
    return {
        "Excellent": float(raw_bands.get("Excellent", DEFAULT_SCORE_BANDS["Excellent"])),
        "Warning": float(raw_bands.get("Warning", DEFAULT_SCORE_BANDS["Warning"])),
        "Failed": float(raw_bands.get("Failed", DEFAULT_SCORE_BANDS["Failed"])),
    }


def _classify_status(score: float, score_bands: dict[str, float]) -> str:
    """Classify a score using the configured lower-bound thresholds."""

    if score >= score_bands["Excellent"]:
        return "Excellent"
    if score >= score_bands["Warning"]:
        return "Warning"
    return "Failed"


def calculate_quality_score(
    issues: list[Issue],
    total_rows: int,
    rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate sub-scores and an overall quality score.

    The function stays side-effect free so it can be tested independently.
    When rules are provided, the score bands and required column counts come
    from the loaded config. If rules are omitted, default thresholds are used.
    """

    analysis_mode = str((rules or {}).get("_analysis_mode", "structured"))
    required_columns = (rules or {}).get("required_columns", [])
    required_column_count = len(required_columns)

    range_columns = (rules or {}).get("ranges", {})
    validity_column_count = len(range_columns) + (
        1 if (rules or {}).get("allowed_nutrition_grades") else 0
    )

    analysis_column_count = max(1, _runtime_count(rules, "_analysis_columns_count", required_column_count))
    numeric_column_count = max(
        0,
        _runtime_count(rules, "_numeric_columns_count", len(range_columns)),
    )
    categorical_column_count = max(
        0,
        _runtime_count(rules, "_categorical_columns_count", 0),
    )
    identifier_column_count = max(
        0,
        _runtime_count(rules, "_identifier_columns_count", 0),
    )

    completeness_penalty = _sum_issue_counts(issues, {"missing_values"})
    validity_penalty = _sum_issue_counts(
        issues,
        {"out_of_range", "unexpected_values", "rare_values"},
    )
    uniqueness_penalty = _sum_issue_counts(
        issues,
        {"duplicate_rows", "duplicate_barcodes", "duplicate_identifiers"},
    )
    consistency_penalty = _sum_issue_counts(issues, {"iqr_outliers"})

    if analysis_mode == "generic":
        # completeness = 100 - (total missing values / (total_rows * total_column_count) * 100)
        completeness_denominator = total_rows * analysis_column_count

        # validity = 100 - (total invalid values / (total_rows * (numeric_column_count + categorical_column_count)) * 100)
        validity_denominator = total_rows * max(1, numeric_column_count + categorical_column_count)

        # uniqueness = 100 - (total duplicate rows / (total_rows * (1 + identifier_column_count)) * 100)
        uniqueness_denominator = total_rows * max(1, 1 + identifier_column_count)

        # consistency = 100 - (total IQR outliers / (total_rows * numeric_column_count) * 100)
        consistency_denominator = total_rows * max(1, numeric_column_count)
    else:
        # completeness = 100 - (total missing values / (total_rows * required_column_count) * 100)
        completeness_denominator = total_rows * max(1, required_column_count)

        # validity = 100 - (total invalid values / (total_rows * validity_column_count) * 100)
        validity_denominator = total_rows * max(1, validity_column_count)

        # uniqueness = 100 - (total duplicate rows / (total_rows * 2) * 100)
        uniqueness_denominator = total_rows * 2

        # consistency = 100 - (total IQR outliers / (total_rows * 3) * 100)
        consistency_denominator = total_rows * 3

    completeness = _score_from_penalty(
        completeness_penalty,
        completeness_denominator,
    )

    validity = _score_from_penalty(
        validity_penalty,
        validity_denominator,
    )

    uniqueness = _score_from_penalty(
        uniqueness_penalty,
        uniqueness_denominator,
    )

    consistency = _score_from_penalty(
        consistency_penalty,
        consistency_denominator,
    )

    overall_score = (
        completeness * 0.30
        + validity * 0.30
        + uniqueness * 0.20
        + consistency * 0.20
    )
    overall_score = round(overall_score, 1)

    score_bands = _normalize_score_bands(rules)
    status = _classify_status(overall_score, score_bands)

    return {
        "overall_score": overall_score,
        "status": status,
        "completeness": round(completeness, 1),
        "validity": round(validity, 1),
        "uniqueness": round(uniqueness, 1),
        "consistency": round(consistency, 1),
    }
