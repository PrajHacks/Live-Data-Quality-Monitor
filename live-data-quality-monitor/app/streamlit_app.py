"""Streamlit interface for the Live Data Quality Monitor."""

from __future__ import annotations

from html import escape as html_escape
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.fetch_live_data import (  # noqa: E402
    TARGET_ROWS,
    build_dataframe,
    fetch_products,
    save_outputs,
)
import src.email_sender as email_sender_module  # noqa: E402
import src.database as database_module  # noqa: E402
from src.pdf_report_generator import generate_pdf_report  # noqa: E402
from src.report_generator import generate_excel_report  # noqa: E402
from src.validator import load_rules, validate_dataframe  # noqa: E402

send_report_email = email_sender_module.send_report_email
get_recent_runs = database_module.get_recent_runs
save_issues = database_module.save_issues
save_run_results = database_module.save_run_results
logger = logging.getLogger(__name__)


REPORTS_DIR = PROJECT_ROOT / "reports"
PRIMARY_ACCENT = "#2DD4BF"
SECONDARY_ACCENT = "#38BDF8"
SURFACE_BORDER = "rgba(148, 163, 184, 0.18)"
SURFACE_BG = "rgba(15, 23, 42, 0.76)"
SURFACE_BG_SOFT = "rgba(15, 23, 42, 0.46)"
HEADER_GRADIENT = "linear-gradient(135deg, rgba(45, 212, 191, 0.12), rgba(56, 189, 248, 0.10))"

STATUS_STYLES = {
    "Excellent": {
        "background": "#D9EAD3",
        "border": "#93C47D",
        "text": "#274E13",
    },
    "Warning": {
        "background": "#FFF2CC",
        "border": "#E6B800",
        "text": "#7F6000",
    },
    "Failed": {
        "background": "#F4CCCC",
        "border": "#CC0000",
        "text": "#7F1D1D",
    },
}

SEVERITY_ORDER = ["Critical", "Warning", "Info"]
SEVERITY_COLORS = {
    "Critical": "#D9534F",
    "Warning": "#F0AD4E",
    "Info": "#5B9BD5",
}
METRICS = [
    ("C", "Completeness", "completeness", "Missing values across the dataset"),
    ("V", "Validity", "validity", "Range and value checks"),
    ("U", "Uniqueness", "uniqueness", "Duplicate detection"),
    ("S", "Consistency", "consistency", "Outlier detection"),
]

ABOUT_TEXT = (
    "This demo shows how companies can automate data quality monitoring for "
    "their own datasets. Instead of manually checking incoming data for "
    "missing values, duplicates, and invalid entries, the pipeline runs "
    "automatically, scores the data, generates Excel and PDF reports, and "
    "emails stakeholders when quality drops below a threshold. This pattern "
    "applies to retail, e-commerce, healthcare, finance, and any industry "
    "that ingests data from multiple sources and needs to trust it before "
    "using it for decisions."
)


def is_email_configured() -> bool:
    """Return True when the email helper exposes a working configuration check."""

    checker = getattr(email_sender_module, "is_email_configured", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            return False
    return False


def is_mysql_configured() -> bool:
    """Return True when the database helper exposes a working configuration check."""

    checker = getattr(database_module, "is_mysql_configured", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            return False
    return False


def inject_custom_styles() -> None:
    """Apply a cohesive dark UI style to the app."""

    st.markdown(
        f"""
        <style>
            .stApp {{
                background:
                    radial-gradient(circle at 12% 8%, rgba(45, 212, 191, 0.12), transparent 24%),
                    radial-gradient(circle at 88% 4%, rgba(56, 189, 248, 0.11), transparent 22%),
                    linear-gradient(180deg, #07111E 0%, #0B1220 44%, #0B1220 100%);
                color: #E2E8F0;
            }}
            section[data-testid="stSidebar"] {{
                background:
                    linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(15, 23, 42, 0.92));
                border-right: 1px solid rgba(148, 163, 184, 0.12);
            }}
            section[data-testid="stSidebar"] > div {{
                padding-top: 1.1rem;
            }}
            .main .block-container {{
                padding-top: 1.15rem;
                padding-bottom: 2.5rem;
            }}
            .hero-card {{
                padding: 1.35rem 1.5rem 1.4rem;
                border-radius: 24px;
                border: 1px solid {SURFACE_BORDER};
                background: {HEADER_GRADIENT}, linear-gradient(135deg, rgba(15, 23, 42, 0.98), rgba(15, 23, 42, 0.74));
                box-shadow: 0 22px 50px rgba(2, 6, 23, 0.38);
            }}
            .hero-kicker {{
                color: {PRIMARY_ACCENT};
                font-size: 0.78rem;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 0.18em;
                margin-bottom: 0.35rem;
            }}
            .hero-title {{
                color: #F8FAFC;
                font-size: 2.15rem;
                line-height: 1.1;
                font-weight: 900;
                margin: 0;
            }}
            .hero-subtitle {{
                color: #CBD5E1;
                font-size: 1rem;
                line-height: 1.55;
                margin-top: 0.55rem;
                max-width: 72ch;
            }}
            .score-card {{
                padding: 1.35rem 1.45rem 1.25rem;
                border-radius: 24px;
                border: 1px solid {SURFACE_BORDER};
                background: linear-gradient(180deg, rgba(15, 23, 42, 0.97), rgba(15, 23, 42, 0.82));
                box-shadow: 0 20px 40px rgba(2, 6, 23, 0.28);
                margin-bottom: 0.25rem;
            }}
            .score-label {{
                color: #CBD5E1;
                font-size: 0.82rem;
                font-weight: 800;
                letter-spacing: 0.16em;
                text-transform: uppercase;
                margin-bottom: 0.35rem;
            }}
            .score-value {{
                color: #F8FAFC;
                font-size: 4.35rem;
                font-weight: 900;
                line-height: 0.95;
                margin: 0.05rem 0 0.45rem;
            }}
            .score-pill {{
                display: inline-flex;
                align-items: center;
                gap: 0.45rem;
                padding: 0.46rem 0.88rem;
                border-radius: 999px;
                font-size: 0.88rem;
                font-weight: 800;
                letter-spacing: 0.03em;
                border: 1px solid transparent;
            }}
            .score-pill.excellent {{
                color: #BBF7D0;
                background: rgba(34, 197, 94, 0.16);
                border-color: rgba(34, 197, 94, 0.35);
            }}
            .score-pill.warning {{
                color: #FDE68A;
                background: rgba(250, 204, 21, 0.16);
                border-color: rgba(250, 204, 21, 0.35);
            }}
            .score-pill.failed {{
                color: #FECACA;
                background: rgba(248, 113, 113, 0.16);
                border-color: rgba(248, 113, 113, 0.35);
            }}
            .metric-card {{
                height: 100%;
                padding: 1rem 1rem 0.9rem;
                border-radius: 20px;
                border: 1px solid {SURFACE_BORDER};
                background:
                    linear-gradient(180deg, rgba(17, 28, 46, 0.92), rgba(15, 23, 42, 0.82));
                box-shadow: 0 14px 26px rgba(2, 6, 23, 0.18);
            }}
            .metric-icon {{
                width: 2rem;
                height: 2rem;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: 999px;
                font-size: 0.85rem;
                font-weight: 900;
                letter-spacing: 0.08em;
                color: #0F172A;
                background: linear-gradient(135deg, rgba(45, 212, 191, 0.95), rgba(56, 189, 248, 0.95));
                line-height: 1;
                margin-bottom: 0.6rem;
            }}
            .metric-label {{
                color: #C4D5E6;
                font-size: 0.83rem;
                font-weight: 800;
                letter-spacing: 0.11em;
                text-transform: uppercase;
            }}
            .metric-value {{
                color: #F8FAFC;
                font-size: 2.18rem;
                font-weight: 900;
                line-height: 1.05;
                margin-top: 0.35rem;
            }}
            .metric-note {{
                color: #94A3B8;
                font-size: 0.82rem;
                margin-top: 0.28rem;
            }}
            .recent-runs-wrap {{
                overflow-x: auto;
                border-radius: 18px;
                border: 1px solid {SURFACE_BORDER};
                background: {SURFACE_BG};
                box-shadow: 0 14px 26px rgba(2, 6, 23, 0.18);
            }}
            .recent-runs-table {{
                width: 100%;
                border-collapse: collapse;
                color: #E2E8F0;
            }}
            .recent-runs-table thead th {{
                padding: 0.88rem 1rem;
                text-align: left;
                font-size: 0.8rem;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: #94A3B8;
                background: rgba(15, 23, 42, 0.96);
                border-bottom: 1px solid {SURFACE_BORDER};
            }}
            .recent-runs-table tbody td {{
                padding: 0.85rem 1rem;
                border-bottom: 1px solid rgba(148, 163, 184, 0.12);
                vertical-align: middle;
            }}
            .recent-runs-table tbody tr:nth-child(even) td {{
                background: rgba(15, 23, 42, 0.32);
            }}
            .run-status-badge {{
                display: inline-flex;
                align-items: center;
                gap: 0.35rem;
                padding: 0.3rem 0.72rem;
                border-radius: 999px;
                font-size: 0.8rem;
                font-weight: 800;
                white-space: nowrap;
            }}
            .run-status-excellent {{
                color: #BBF7D0;
                background: rgba(34, 197, 94, 0.16);
                border: 1px solid rgba(34, 197, 94, 0.35);
            }}
            .run-status-warning {{
                color: #FDE68A;
                background: rgba(250, 204, 21, 0.16);
                border: 1px solid rgba(250, 204, 21, 0.35);
            }}
            .run-status-failed {{
                color: #FECACA;
                background: rgba(248, 113, 113, 0.16);
                border: 1px solid rgba(248, 113, 113, 0.35);
            }}
            .run-status-info {{
                color: #BFDBFE;
                background: rgba(96, 165, 250, 0.16);
                border: 1px solid rgba(96, 165, 250, 0.35);
            }}
            div[data-testid="stStatus"] {{
                border-radius: 18px;
                border: 1px solid rgba(45, 212, 191, 0.18);
                background: rgba(15, 23, 42, 0.70);
                box-shadow: 0 14px 28px rgba(2, 6, 23, 0.18);
            }}
            div[data-testid="stExpander"] {{
                border-radius: 18px;
                border: 1px solid {SURFACE_BORDER};
                background: rgba(15, 23, 42, 0.62);
                box-shadow: 0 12px 24px rgba(2, 6, 23, 0.16);
            }}
            div[data-testid="stDataFrame"] {{
                border-radius: 16px;
                overflow: hidden;
                border: 1px solid {SURFACE_BORDER};
            }}
            .stAlert {{
                border-radius: 16px;
            }}
            .stCaption {{
                color: #94A3B8;
            }}
            [data-testid="stButton"] > button,
            [data-testid="stDownloadButton"] > button {{
                border-radius: 999px !important;
                border: 1px solid rgba(45, 212, 191, 0.35) !important;
                background: linear-gradient(135deg, rgba(14, 26, 47, 0.96), rgba(17, 29, 51, 0.92)) !important;
                color: #E2E8F0 !important;
                font-weight: 700 !important;
                padding: 0.7rem 1rem !important;
                transition:
                    transform 0.18s ease,
                    border-color 0.18s ease,
                    box-shadow 0.18s ease,
                    filter 0.18s ease !important;
            }}
            [data-testid="stButton"] > button:hover,
            [data-testid="stDownloadButton"] > button:hover {{
                transform: translateY(-1px);
                border-color: {PRIMARY_ACCENT} !important;
                box-shadow: 0 12px 22px rgba(45, 212, 191, 0.14);
                filter: brightness(1.06);
            }}
            [data-testid="stButton"] > button:focus-visible,
            [data-testid="stDownloadButton"] > button:focus-visible {{
                outline: 2px solid rgba(45, 212, 191, 0.55);
                outline-offset: 2px;
            }}
            section[data-testid="stSidebar"] [data-testid="stButton"] > button,
            section[data-testid="stSidebar"] [data-testid="stDownloadButton"] > button {{
                background: linear-gradient(135deg, rgba(45, 212, 191, 0.18), rgba(56, 189, 248, 0.18)) !important;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_class(status: Any) -> str:
    """Map a status label to a CSS class name."""

    normalized = normalize_status_label(status, default="Info").lower()
    if normalized == "excellent":
        return "excellent"
    if normalized == "warning":
        return "warning"
    if normalized == "failed":
        return "failed"
    return "info"


def status_badge_html(status: Any) -> str:
    """Render a small color-coded badge for a validation status."""

    label = str(status).strip() or "Unknown"
    label_key = normalize_status_label(label, default="Info")
    css_class = status_class(label_key)
    return f'<span class="run-status-badge run-status-{css_class}">{html_escape(label_key)}</span>'


def humanize_number(value: Any, digits: int = 1, suffix: str = "%") -> str:
    """Format numeric output consistently for the dashboard."""

    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return ""


def normalize_status_label(status: Any, default: str = "Warning") -> str:
    """Normalize a status value to one of the known display labels."""

    label = str(status).strip().title() or default
    return label if label in STATUS_STYLES else default


def render_hero_header() -> None:
    """Render the title and tagline block at the top of the dashboard."""

    st.markdown(
        """
        <div class="hero-card">
            <div class="hero-kicker">Live Data Quality Monitor</div>
            <div class="hero-title">Data Quality Results</div>
            <div class="hero-subtitle">
                Automated data quality monitoring for any dataset - live API or your own CSV.
                Pick a source in the sidebar, then run the checks to review the score, issues,
                and downloadable reports.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_overall_score(score_result: dict[str, Any]) -> None:
    """Render the large quality score card with a badge-style status."""

    status = normalize_status_label(score_result.get("status", "Warning"))
    overall_score = float(score_result.get("overall_score", 0.0))
    css_class = status_class(status)
    style = STATUS_STYLES.get(status, STATUS_STYLES["Warning"])

    st.markdown(
        f"""
        <div class="score-card">
            <div class="score-label">Overall Quality Score</div>
            <div class="score-value" style="color: {style["text"]};">{overall_score:.1f}%</div>
            <div class="score-pill {css_class}">{html_escape(status)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_cards(score_result: dict[str, Any]) -> None:
    """Show the four sub-scores as polished cards."""

    columns = st.columns(4, gap="small")
    for column, (icon, label, key, note) in zip(columns, METRICS):
        value = humanize_number(score_result.get(key, 0.0))
        column.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-icon">{icon}</div>
                <div class="metric-label">{html_escape(label)}</div>
                <div class="metric-value">{value}</div>
                <div class="metric-note">{html_escape(note)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def recent_runs_html(recent_runs: list[dict[str, Any]]) -> str:
    """Render a compact HTML table for the recent runs panel."""

    rows = []
    for run in recent_runs:
        timestamp = pd.to_datetime(run.get("run_timestamp"), errors="coerce")
        timestamp_text = timestamp.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(timestamp) else ""
        score_text = humanize_number(run.get("overall_score", 0.0))
        rows.append(
            "<tr>"
            f"<td>{html_escape(timestamp_text)}</td>"
            f"<td>{html_escape(str(run.get('total_rows', '')))}</td>"
            f"<td>{html_escape(score_text)}</td>"
            f"<td>{status_badge_html(run.get('status'))}</td>"
            "</tr>"
        )

    return """
        <div class="recent-runs-wrap">
            <table class="recent-runs-table">
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Rows analyzed</th>
                        <th>Overall score</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
    """.format(rows="".join(rows))


def normalize_column_name(column: Any) -> str:
    """Make the display labels friendlier without changing the stored issue data."""

    if column == "__row__":
        return "duplicate rows"
    return str(column).replace("_", " ").strip().title()


def load_csv_from_upload(uploaded_file) -> pd.DataFrame:
    """Read a user-uploaded CSV into a DataFrame."""

    uploaded_file.seek(0)
    return pd.read_csv(uploaded_file)


def fetch_live_dataframe() -> pd.DataFrame:
    """Reuse the existing fetch script to pull and save fresh Open Food Facts data."""

    rows = fetch_products(target_rows=TARGET_ROWS)
    if not rows:
        raise RuntimeError("No products were returned by the Open Food Facts API.")

    df = build_dataframe(rows)
    save_outputs(df)
    return df


def build_analysis(df: pd.DataFrame, status: Any | None = None) -> dict[str, Any]:
    """Run the validator, score calculator, and report generator for one dataset."""

    rules = load_rules()
    if status is not None:
        status.update(label="Running data quality checks...", state="running", expanded=True)
        status.write("Running data quality checks...")
    context, issues, score_result = validate_dataframe(df, rules)
    if status is not None:
        status.write("Running data quality checks... complete")
        status.update(label="Calculating quality score...", state="running", expanded=True)
        status.write("Calculating quality score... complete")
        status.update(label="Generating reports...", state="running", expanded=True)

    timestamp = datetime.now()
    report_stem = timestamp.strftime("%Y-%m-%d_%H%M%S_%f")
    excel_path = REPORTS_DIR / f"Data_Quality_Report_{report_stem}.xlsx"
    pdf_path = REPORTS_DIR / f"Data_Quality_Report_{report_stem}.pdf"
    generated_excel_path = generate_excel_report(df, issues, score_result, excel_path)
    generated_pdf_path = generate_pdf_report(df, issues, score_result, pdf_path)
    if status is not None:
        status.write("Generating reports... complete")
    completed_at = datetime.now()

    return {
        "df": df,
        "issues": issues,
        "score_result": score_result,
        "validation_mode": context["mode"],
        "validation_note": context["mode_message"],
        "excel_path": generated_excel_path,
        "excel_bytes": generated_excel_path.read_bytes(),
        "pdf_path": generated_pdf_path,
        "pdf_bytes": generated_pdf_path.read_bytes(),
        "analysis_token": completed_at.strftime("%Y%m%d%H%M%S%f"),
        "last_analyzed": completed_at.strftime("%Y-%m-%d %H:%M:%S.%f"),
    }


def save_analysis_to_database(
    score_result: dict[str, Any],
    issues: list[dict[str, Any]],
    total_rows: int,
) -> tuple[int | None, str, str]:
    """Persist one analysis run and its issues to MySQL."""

    try:
        run_id = save_run_results(score_result, total_rows)
        save_issues(run_id, issues)
        return run_id, f"Saved to database (Run ID: {run_id})", "success"
    except RuntimeError as exc:
        logger.exception("MySQL persistence failed for the current analysis run.")
        return (
            None,
            "Database persistence isn't available in this environment right now. "
            "You can still use the reports above, and recent runs may be unavailable.",
            "info",
        )


def issue_dataframe(issues: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert the issue list into a table for display and charting."""

    if not issues:
        return pd.DataFrame(columns=["column", "issue_type", "count", "severity", "details"])

    frame = pd.DataFrame(issues)
    expected_columns = ["column", "issue_type", "count", "severity", "details"]
    for column in expected_columns:
        if column not in frame.columns:
            frame[column] = None
    return frame[expected_columns]


def severity_summary(issues: list[dict[str, Any]]) -> pd.DataFrame:
    """Aggregate issue counts by severity for the severity bar chart."""

    issue_df = issue_dataframe(issues)
    if issue_df.empty:
        return pd.DataFrame(
            {
                "severity": SEVERITY_ORDER,
                "issue_count": [0, 0, 0],
            }
        )

    summary = (
        issue_df.groupby("severity", as_index=False)["count"]
        .sum()
        .rename(columns={"count": "issue_count"})
    )
    summary = (
        summary.set_index("severity")
        .reindex(SEVERITY_ORDER, fill_value=0)
        .reset_index()
    )
    return summary


def column_summary(issues: list[dict[str, Any]]) -> pd.DataFrame:
    """Aggregate issue counts by affected column for the column bar chart."""

    issue_df = issue_dataframe(issues)
    if issue_df.empty:
        return pd.DataFrame(columns=["column", "issue_count"])

    summary = issue_df.copy()
    summary["column"] = summary["column"].map(normalize_column_name)
    summary = (
        summary.groupby("column", as_index=False)["count"]
        .sum()
        .rename(columns={"count": "issue_count"})
        .sort_values("issue_count", ascending=True)
    )
    return summary


def status_banner(score_result: dict[str, Any]) -> None:
    """Render the large score display with Excel-matching status colors."""

    render_overall_score(score_result)


def render_metrics(score_result: dict[str, Any]) -> None:
    """Show the four sub-scores as simple summary cards."""

    render_metric_cards(score_result)


def render_charts(issues: list[dict[str, Any]]) -> None:
    """Draw the issue charts with consistent card styling."""

    severity_df = severity_summary(issues)
    column_df = column_summary(issues)

    chart_left, chart_right = st.columns(2)

    with chart_left:
        with st.container(border=True):
            st.markdown("##### Issue severity breakdown")
            st.caption("How the current dataset is distributed across critical, warning, and info findings.")
            severity_fig = px.bar(
                severity_df,
                x="severity",
                y="issue_count",
                text="issue_count",
                color="severity",
                color_discrete_map=SEVERITY_COLORS,
                category_orders={"severity": SEVERITY_ORDER},
                title=None,
            )
            severity_fig.update_layout(
                template="plotly_dark",
                showlegend=False,
                height=420,
                xaxis_title=None,
                yaxis_title="Issue count",
                margin=dict(l=12, r=12, t=15, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                bargap=0.28,
            )
            severity_fig.update_traces(
                marker_line_color="rgba(255,255,255,0.12)",
                marker_line_width=1,
                textposition="outside",
                cliponaxis=False,
            )
            severity_fig.update_xaxes(color="#CBD5E1", showgrid=False)
            severity_fig.update_yaxes(color="#CBD5E1", gridcolor="rgba(148, 163, 184, 0.12)")
            st.plotly_chart(severity_fig, use_container_width=True, config={"displayModeBar": False})

    with chart_right:
        with st.container(border=True):
            st.markdown("##### Issue count by column")
            st.caption("The columns with the most findings surface here first.")
            if column_df.empty:
                st.info("No column issues to show.")
            else:
                column_fig = px.bar(
                    column_df,
                    x="issue_count",
                    y="column",
                    orientation="h",
                    text="issue_count",
                    color_discrete_sequence=[SECONDARY_ACCENT],
                    title=None,
                )
                column_fig.update_layout(
                    template="plotly_dark",
                    showlegend=False,
                    height=420,
                    xaxis_title="Issue count",
                    yaxis_title=None,
                    margin=dict(l=12, r=12, t=15, b=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    bargap=0.28,
                )
                column_fig.update_traces(
                    marker_line_color="rgba(255,255,255,0.12)",
                    marker_line_width=1,
                    textposition="outside",
                    cliponaxis=False,
                )
                column_fig.update_xaxes(color="#CBD5E1", gridcolor="rgba(148, 163, 184, 0.12)")
                column_fig.update_yaxes(color="#CBD5E1", showgrid=False)
                st.plotly_chart(column_fig, use_container_width=True, config={"displayModeBar": False})


def render_section_divider() -> None:
    """Add a subtle divider between major sections."""

    st.divider()


def render_no_analysis_placeholder() -> None:
    """Show the empty-state guidance before the first analysis."""

    st.info("Pick a source, click Analyze, and your results will appear here.")


def render_issue_table(issues: list[dict[str, Any]]) -> None:
    """Show the detailed issue table in an expandable section."""

    with st.expander("View all issues", expanded=False):
        issue_df = issue_dataframe(issues)
        if issue_df.empty:
            st.success("No issues were found for this dataset.")
        else:
            st.dataframe(issue_df, use_container_width=True)


def render_downloads(excel_path: Path, excel_bytes: bytes, pdf_path: Path, pdf_bytes: bytes) -> None:
    """Offer the generated Excel and PDF reports as downloads."""

    with st.container(border=True):
        st.markdown("##### Export reports")
        st.caption("Download the current analysis as either a spreadsheet or a printable PDF.")
        excel_col, pdf_col = st.columns(2, gap="small")
        with excel_col:
            st.download_button(
                "Download Excel",
                data=excel_bytes,
                file_name=excel_path.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="download_excel_report",
                icon="\U0001F4CA",
            )
        with pdf_col:
            st.download_button(
                "Download PDF",
                data=pdf_bytes,
                file_name=pdf_path.name,
                mime="application/pdf",
                use_container_width=True,
                key="download_pdf_report",
                icon="\U0001F4C4",
            )


def render_email_section(analysis: dict[str, Any] | None) -> None:
    """Render the email form and send the current report when requested."""

    with st.expander("Email this report", expanded=False):
        with st.container(border=True):
            recipient_email = st.text_input(
                "Recipient email",
                key="recipient_email_input",
                placeholder="name@example.com",
            )

            send_clicked = st.button(
                "Send Report",
                key="send_report_button",
                use_container_width=True,
                icon="\U0001F4E7",
                type="primary",
            )

            if send_clicked and analysis:
                if not recipient_email.strip():
                    st.info("Please enter a recipient email address.")
                    return

                result = send_report_email(
                    recipient_email=recipient_email,
                    score_result=analysis["score_result"],
                    excel_path=analysis["excel_path"],
                    pdf_path=analysis["pdf_path"],
                    issues=analysis["issues"],
                )
                if result.get("success"):
                    st.success(result["message"])
                else:
                    st.info(result["message"])


def render_about_section() -> None:
    """Show a minimal footnote-style explanation in the sidebar."""

    st.sidebar.caption(f"About / Use Case: {ABOUT_TEXT}")


def format_recent_runs_table(recent_runs: list[dict[str, Any]]) -> pd.DataFrame:
    """Prepare historical runs for display in the UI."""

    frame = pd.DataFrame(recent_runs)
    if frame.empty:
        return pd.DataFrame(
            columns=["Timestamp", "Rows analyzed", "Overall score", "Status"]
        )

    frame["run_timestamp"] = pd.to_datetime(frame["run_timestamp"], errors="coerce")
    frame["status"] = frame["status"].map(lambda value: str(value))
    frame["overall_score"] = pd.to_numeric(frame["overall_score"], errors="coerce")
    frame["run_timestamp"] = frame["run_timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

    display_frame = frame.rename(
        columns={
            "run_timestamp": "Timestamp",
            "total_rows": "Rows analyzed",
            "overall_score": "Overall score",
            "status": "Status",
        }
    )[["Timestamp", "Rows analyzed", "Overall score", "Status"]]
    display_frame["Overall score"] = display_frame["Overall score"].map(
        lambda value: f"{float(value):.1f}%" if pd.notna(value) else ""
    )
    return display_frame


def render_recent_runs_panel(limit: int = 10) -> None:
    """Show the most recent database-backed validation runs."""

    with st.expander("Recent Runs", expanded=False):
        st.caption(
            "Historical validation runs stored in MySQL. Timestamps include seconds."
        )

        try:
            recent_runs = get_recent_runs(limit=limit)
        except RuntimeError as exc:
            logger.exception("Failed to load recent runs from MySQL.")
            st.info(
                "Recent runs are temporarily unavailable in this environment right now."
            )
            return

        if not recent_runs:
            st.info("No previous runs found.")
            return

        st.markdown(recent_runs_html(recent_runs), unsafe_allow_html=True)

        trend_df = pd.DataFrame(recent_runs).copy()
        trend_df["run_timestamp"] = pd.to_datetime(trend_df["run_timestamp"], errors="coerce")
        trend_df["overall_score"] = pd.to_numeric(trend_df["overall_score"], errors="coerce")
        trend_df = trend_df.dropna(subset=["run_timestamp", "overall_score"]).sort_values(
            "run_timestamp"
        )

        if len(trend_df) >= 2:
            trend_fig = px.line(
                trend_df,
                x="run_timestamp",
                y="overall_score",
                markers=True,
                title="Score trend over recent runs",
                color_discrete_sequence=[PRIMARY_ACCENT],
            )
            trend_fig.update_layout(
                template="plotly_dark",
                showlegend=False,
                height=330,
                xaxis_title=None,
                yaxis_title="Overall score (%)",
                margin=dict(l=12, r=12, t=28, b=10),
                title=dict(x=0.02, xanchor="left", font=dict(size=16, color="#E2E8F0")),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            trend_fig.update_yaxes(range=[0, 100])
            trend_fig.update_xaxes(color="#CBD5E1", gridcolor="rgba(148, 163, 184, 0.12)")
            trend_fig.update_yaxes(color="#CBD5E1", gridcolor="rgba(148, 163, 184, 0.12)")
            st.plotly_chart(trend_fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("Need at least two runs to show a trend line.")


def main() -> None:
    """Render the Streamlit dashboard and react to the Analyze action."""

    st.set_page_config(
        page_title="Live Data Quality Monitor",
        page_icon="DQ",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    inject_custom_styles()

    st.sidebar.title("Live Data Quality Monitor")
    with st.sidebar.container(border=True):
        st.markdown("**Run an analysis**")
        source_mode = st.radio(
            "Choose a data source",
            ("Fetch Live Data", "Upload CSV"),
        )

        uploaded_file = None
        if source_mode == "Upload CSV":
            uploaded_file = st.file_uploader(
                "Upload a CSV file",
                type=["csv"],
                help="Upload any product CSV to check its data quality.",
            )
        else:
            st.caption(
                "The app will fetch a fresh extract from Open Food Facts when you analyze."
            )

        analyze_clicked = st.button(
            "Analyze",
            use_container_width=True,
            type="primary",
        )

    st.sidebar.divider()
    render_about_section()

    render_hero_header()
    st.divider()

    if analyze_clicked:
        st.session_state.pop("analysis", None)
        status = None
        analysis_error = None
        try:
            if source_mode == "Upload CSV" and uploaded_file is None:
                analysis_error = "Please upload a CSV file before clicking Analyze."
                st.warning(analysis_error)
            else:
                status_label = (
                    "Fetching live product data from Open Food Facts..."
                    if source_mode == "Fetch Live Data"
                    else "Loading uploaded CSV..."
                )

                with st.status(status_label, expanded=True) as status:
                    if source_mode == "Fetch Live Data":
                        status.write(
                            "This can take 30-60 seconds depending on the live API response time - thanks for your patience!"
                        )
                        status.write("Fetching live product data from Open Food Facts...")
                        df = fetch_live_dataframe()
                        status.write("Fetching live product data from Open Food Facts... complete")
                        if len(df) < TARGET_ROWS:
                            st.warning(
                                f"The live fetch returned {len(df)} rows, which is fewer than the "
                                f"target of {TARGET_ROWS}."
                            )
                    else:
                        status.write("Loading uploaded CSV...")
                        df = load_csv_from_upload(uploaded_file)
                        status.write("Loading uploaded CSV... complete")

                    status.update(label="Running data quality checks...", state="running", expanded=True)
                    status.write("Running data quality checks...")
                    analysis = build_analysis(df, status=status)
                    status.write("Running data quality checks... complete")

                    status.update(label="Saving results to database...", state="running", expanded=True)
                    status.write("Saving results to database...")
                    if st.session_state.get("last_saved_analysis_token") == analysis["analysis_token"]:
                        run_id = st.session_state.get("last_saved_run_id")
                        analysis["db_message"] = f"Saved to database (Run ID: {run_id})"
                        analysis["db_message_level"] = "success"
                    else:
                        run_id, db_message, db_message_level = save_analysis_to_database(
                            analysis["score_result"],
                            analysis["issues"],
                            len(df),
                        )
                        analysis["db_message"] = db_message
                        analysis["db_message_level"] = db_message_level
                        if run_id is not None:
                            st.session_state["last_saved_analysis_token"] = analysis["analysis_token"]
                            st.session_state["last_saved_run_id"] = run_id
                    if run_id is not None:
                        status.write(f"Saving results to database... complete (Run ID: {run_id})")
                    else:
                        status.write("Saving results to database... unavailable")

                    status.update(label="Analysis complete", state="complete", expanded=False)
                st.caption(
                    "This can take 30-60 seconds depending on the live API response time - thanks for your patience!"
                )
                st.session_state.analysis = analysis
                st.success("Analysis complete.")
        except Exception as exc:
            if status is not None:
                status.update(label="Analysis failed", state="error", expanded=True)
            st.error(f"Unable to analyze the selected data: {exc}")

    analysis = st.session_state.get("analysis")
    if analysis:
        score_result = analysis["score_result"]
        issues = analysis["issues"]

        if analysis.get("validation_mode") == "generic":
            st.caption(analysis.get("validation_note"))

        status_banner(score_result)
        render_metrics(score_result)
        st.divider()
        render_charts(issues)
        st.divider()
        render_issue_table(issues)

        st.divider()
        render_downloads(
            analysis["excel_path"],
            analysis["excel_bytes"],
            analysis["pdf_path"],
            analysis["pdf_bytes"],
        )
        db_message = analysis.get("db_message")
        if db_message:
            message_level = analysis.get("db_message_level", "success")
            if message_level == "success":
                st.success(db_message)
            else:
                st.info(db_message)
        st.caption(f"Last analyzed: {analysis['last_analyzed']}")
        render_email_section(analysis)
    else:
        render_no_analysis_placeholder()

    st.divider()
    render_recent_runs_panel()


if __name__ == "__main__":
    main()
