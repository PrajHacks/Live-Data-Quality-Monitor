"""Run the validation rules against the latest Open Food Facts extract."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.category_checker import check_nutrition_grades
from src.database import save_issues, save_run_results
from src.duplicate_checker import check_duplicates
from src.missing_checker import check_missing_values
from src.schema_detector import detect_schema, is_open_food_facts_schema
from src.report_generator import generate_excel_report
from src.quality_score import calculate_quality_score
from src.outlier_checker import check_outliers
from src.range_checker import check_ranges


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = PROJECT_ROOT / "config" / "rules.json"
DATA_DIR = PROJECT_ROOT / "data" / "incoming"
REPORTS_DIR = PROJECT_ROOT / "reports"

Issue = dict[str, Any]

SEVERITY_ORDER = {
    "Critical": 0,
    "Warning": 1,
    "Info": 2,
}


def load_rules(rules_path: Path = RULES_PATH) -> dict[str, Any]:
    """Load the validation rules from JSON."""

    with rules_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_latest_dataframe(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Load products_latest.csv, or the newest products_*.csv as a fallback."""

    latest_csv = data_dir / "products_latest.csv"
    if latest_csv.exists():
        return pd.read_csv(latest_csv)

    candidates = sorted(
        data_dir.glob("products_*.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No CSV files found in {data_dir}. Expected products_latest.csv "
            "or a timestamped products_*.csv file."
        )

    return pd.read_csv(candidates[0])


def build_validation_context(df: pd.DataFrame, rules: dict[str, Any]) -> dict[str, Any]:
    """Detect the right validation mode and attach runtime schema metadata."""

    schema = detect_schema(df)
    structured_match = is_open_food_facts_schema(df, rules)
    mode = "structured" if structured_match["is_match"] else "generic"
    runtime_rules = deepcopy(rules)
    schema_summary = schema.get("summary", {})

    runtime_rules.update(
        {
            "_analysis_mode": mode,
            "_schema_detection": schema,
            "_structured_schema_match": structured_match,
            "_analysis_columns_count": len(df.columns),
            "_numeric_columns_count": int(schema_summary.get("numeric_count", 0)),
            "_categorical_columns_count": int(schema_summary.get("categorical_count", 0)),
            "_identifier_columns_count": int(schema_summary.get("identifier_count", 0)),
            "_date_columns_count": int(schema_summary.get("date_count", 0)),
            "_text_columns_count": int(schema_summary.get("text_count", 0)),
        }
    )

    if mode == "structured":
        mode_message = (
            "Using the built-in Open Food Facts schema because the uploaded data "
            "closely matches the expected product columns."
        )
    else:
        mode_message = (
            "Analyzing with automatic schema detection since this doesn't match "
            "the built-in product data schema."
        )

    return {
        "mode": mode,
        "mode_message": mode_message,
        "match_ratio": float(structured_match.get("match_ratio", 0.0)),
        "schema": schema,
        "rules": runtime_rules,
    }


def validate_dataframe(df: pd.DataFrame, rules: dict[str, Any]) -> tuple[dict[str, Any], list[Issue], dict[str, Any]]:
    """Build the runtime context, run the checks, and calculate the score."""

    context = build_validation_context(df, rules)
    issues = run_validations(df, context["rules"])
    quality_report = calculate_quality_score(issues, len(df), context["rules"])
    quality_report["analysis_mode"] = context["mode"]
    quality_report["schema_match_ratio"] = context["match_ratio"]
    return context, issues, quality_report


def run_validations(df: pd.DataFrame, rules: dict[str, Any]) -> list[Issue]:
    """Run all checkers and combine their results."""

    issues: list[Issue] = []
    checkers = (
        check_missing_values,
        check_duplicates,
        check_ranges,
        check_nutrition_grades,
        check_outliers,
    )

    for checker in checkers:
        issues.extend(checker(df, rules))

    return issues


def format_issue_label(issue: Issue) -> str:
    """Create a readable summary label for a checker result."""

    issue_type = issue["issue_type"]
    column = issue["column"]
    pretty_column = str(column).replace("_", " ").strip().title()

    if issue_type == "missing_values":
        return f"Missing {pretty_column}"
    if issue_type == "duplicate_rows":
        return "Duplicate rows"
    if issue_type == "duplicate_barcodes":
        return "Duplicate barcodes"
    if issue_type == "duplicate_identifiers":
        return f"Duplicate {pretty_column} values"
    if issue_type == "out_of_range":
        return f"{pretty_column} out of range"
    if issue_type == "unexpected_values":
        return f"Unexpected {pretty_column} values"
    if issue_type == "rare_values":
        return f"Rare {pretty_column} values"
    if issue_type == "iqr_outliers":
        return f"{pretty_column} IQR outliers"

    return f"{issue_type} ({pretty_column})"


def print_summary(issues: list[Issue]) -> None:
    """Print a compact summary table to the console."""

    if not issues:
        print("No data quality issues found.")
        return

    ordered = sorted(
        issues,
        key=lambda issue: (
            SEVERITY_ORDER.get(issue["severity"], 99),
            format_issue_label(issue),
        ),
    )
    rows = [
        (format_issue_label(issue), str(issue["count"]), issue["severity"])
        for issue in ordered
    ]

    issue_width = max(len("Issue"), *(len(row[0]) for row in rows))
    count_width = max(len("Count"), *(len(row[1]) for row in rows))
    severity_width = max(len("Severity"), *(len(row[2]) for row in rows))

    header = (
        f"{'Issue'.ljust(issue_width)}  "
        f"{'Count'.rjust(count_width)}  "
        f"{'Severity'.ljust(severity_width)}"
    )
    print(header)
    print("-" * len(header))

    for issue_label, count, severity in rows:
        print(
            f"{issue_label.ljust(issue_width)}  "
            f"{count.rjust(count_width)}  "
            f"{severity.ljust(severity_width)}"
        )


def print_quality_report(report: dict[str, Any], total_rows: int) -> None:
    """Print the weighted quality score report."""

    status_symbol = {
        "Excellent": "\u2705",
        "Warning": "\u26a0\ufe0f",
        "Failed": "\u274c",
    }.get(report["status"], "")

    print("\nDATA QUALITY REPORT")
    print("\u2500" * 32)
    print(f"{'Rows analyzed:':<20}{total_rows:>8}")
    print(f"{'Completeness:':<20}{report['completeness']:>7.1f}%")
    print(f"{'Validity:':<20}{report['validity']:>7.1f}%")
    print(f"{'Uniqueness:':<20}{report['uniqueness']:>7.1f}%")
    print(f"{'Consistency:':<20}{report['consistency']:>7.1f}%")
    print("\u2500" * 32)
    print(f"{'Overall Score:':<20}{report['overall_score']:>7.1f}%")
    print(f"{'Status:':<20}{status_symbol} {report['status']}")


def main() -> list[Issue]:
    """Run the end-to-end validation against products_latest.csv."""

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    rules = load_rules()
    df = load_latest_dataframe()
    context, issues, quality_report = validate_dataframe(df, rules)
    print(f"Validation mode: {context['mode'].title()}")
    print(context["mode_message"])
    print_summary(issues)
    print_quality_report(quality_report, len(df))
    report_timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    report_path = REPORTS_DIR / f"Data_Quality_Report_{report_timestamp}.xlsx"
    generate_excel_report(df, issues, quality_report, report_path)
    print(f"Report saved to: {report_path.relative_to(PROJECT_ROOT).as_posix()}")
    try:
        run_id = save_run_results(quality_report, len(df))
        save_issues(run_id, issues)
        print(f"Saved to database. Run ID: {run_id}")
    except RuntimeError as exc:
        print(f"Database save failed: {exc}")
    return issues


if __name__ == "__main__":
    main()
