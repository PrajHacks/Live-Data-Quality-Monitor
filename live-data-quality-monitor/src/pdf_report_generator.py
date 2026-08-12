"""Generate a concise PDF summary for business stakeholders."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


Issue = dict[str, Any]

SEVERITY_ORDER = {
    "Critical": 0,
    "Warning": 1,
    "Info": 2,
}

STATUS_PALETTE = {
    "Excellent": {
        "fill": colors.HexColor("#D9EAD3"),
        "text": colors.HexColor("#274E13"),
        "accent": colors.HexColor("#6AA84F"),
    },
    "Warning": {
        "fill": colors.HexColor("#FFF2CC"),
        "text": colors.HexColor("#7F6000"),
        "accent": colors.HexColor("#E6B800"),
    },
    "Failed": {
        "fill": colors.HexColor("#F4CCCC"),
        "text": colors.HexColor("#7F1D1D"),
        "accent": colors.HexColor("#CC0000"),
    },
}


def _status_colors(status: str) -> dict[str, colors.Color]:
    """Return a safe palette for the requested score band."""

    return STATUS_PALETTE.get(status, STATUS_PALETTE["Warning"])


def _format_score(value: Any) -> str:
    """Format a score as a percentage string."""

    return f"{float(value):.1f}%"


def _humanize_column_name(column: Any) -> str:
    """Make technical column labels easier to read in the PDF."""

    if column == "__row__":
        return "Duplicate rows"
    return str(column).replace("_", " ").strip().title()


def _humanize_issue_type(issue_type: Any) -> str:
    """Make issue types readable without losing their meaning."""

    mapping = {
        "missing_values": "Missing values",
        "out_of_range": "Out of range",
        "unexpected_values": "Unexpected values",
        "rare_values": "Rare values",
        "duplicate_identifiers": "Duplicate identifiers",
        "iqr_outliers": "IQR outliers",
    }
    raw_value = str(issue_type).strip()
    if raw_value in mapping:
        return mapping[raw_value]
    return raw_value.replace("_", " ").strip().title()


def _sort_issues_for_report(issues: list[Issue]) -> list[Issue]:
    """Sort issues by severity, then by count, for a clean summary."""

    return sorted(
        issues,
        key=lambda issue: (
            SEVERITY_ORDER.get(str(issue.get("severity")), 99),
            -int(issue.get("count", 0)),
            str(issue.get("column", "")),
            str(issue.get("issue_type", "")),
        ),
    )


def _build_styles() -> dict[str, ParagraphStyle]:
    """Create the text styles used throughout the report."""

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#1F1F1F"),
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportMeta",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#4D4D4D"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionHeader",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#1F1F1F"),
            spaceBefore=6,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableCell",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=10,
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableCellCenter",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=10,
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ScoreValue",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=24,
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            name="StatusValue",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=16,
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            name="IssueCell",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=9.5,
            alignment=TA_LEFT,
        )
    )

    return {
        "title": styles["ReportTitle"],
        "meta": styles["ReportMeta"],
        "section": styles["SectionHeader"],
        "cell": styles["TableCell"],
        "cell_center": styles["TableCellCenter"],
        "score": styles["ScoreValue"],
        "status": styles["StatusValue"],
        "issue": styles["IssueCell"],
    }


def _summary_table(score_result: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    """Create the overall score/status banner table."""

    status = str(score_result.get("status", "Warning"))
    palette = _status_colors(status)
    score_value = _format_score(score_result.get("overall_score", 0.0))

    table = Table(
        [
            [
                Paragraph("Overall Score", styles["cell_center"]),
                Paragraph(score_value, styles["score"]),
                Paragraph("Status", styles["cell_center"]),
                Paragraph(status, styles["status"]),
            ]
        ],
        colWidths=[1.25 * inch, 1.6 * inch, 0.95 * inch, 1.95 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), palette["fill"]),
                ("BOX", (0, 0), (-1, -1), 1, palette["accent"]),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("TEXTCOLOR", (0, 0), (0, 0), palette["text"]),
                ("TEXTCOLOR", (1, 0), (1, 0), palette["text"]),
                ("TEXTCOLOR", (2, 0), (2, 0), palette["text"]),
                ("TEXTCOLOR", (3, 0), (3, 0), palette["text"]),
            ]
        )
    )
    return table


def _subscore_table(score_result: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    """Create the table that shows the four component scores."""

    rows = [
        ["Metric", "Score"],
        ["Completeness", _format_score(score_result.get("completeness", 0.0))],
        ["Validity", _format_score(score_result.get("validity", 0.0))],
        ["Uniqueness", _format_score(score_result.get("uniqueness", 0.0))],
        ["Consistency", _format_score(score_result.get("consistency", 0.0))],
    ]

    table = Table(rows, colWidths=[2.1 * inch, 1.0 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LEADING", (0, 0), (-1, -1), 11),
                ("ALIGN", (1, 1), (1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B7B7B7")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9F9F9")]),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _issue_rows(issues: list[Issue], styles: dict[str, ParagraphStyle]) -> list[list[Any]]:
    """Build the issue table rows for the top 10 findings."""

    rows: list[list[Any]] = [
        [
            Paragraph("Column", styles["cell"]),
            Paragraph("Issue type", styles["cell"]),
            Paragraph("Count", styles["cell_center"]),
            Paragraph("Severity", styles["cell_center"]),
        ]
    ]

    top_issues = _sort_issues_for_report(issues)[:10]
    if not top_issues:
        rows.append(
            [
                Paragraph("No issues found", styles["issue"]),
                Paragraph("", styles["issue"]),
                Paragraph("", styles["issue"]),
                Paragraph("", styles["issue"]),
            ]
        )
        return rows

    for issue in top_issues:
        severity = str(issue.get("severity", ""))
        severity_color = {
            "Critical": colors.HexColor("#C00000"),
            "Warning": colors.HexColor("#C65911"),
            "Info": colors.HexColor("#2F75B5"),
        }.get(severity, colors.black)
        severity_hex = f"#{severity_color.hexval()[2:]}"

        rows.append(
            [
                Paragraph(_humanize_column_name(issue.get("column")), styles["issue"]),
                Paragraph(_humanize_issue_type(issue.get("issue_type")), styles["issue"]),
                Paragraph(str(int(issue.get("count", 0))), styles["cell_center"]),
                Paragraph(
                    f'<font color="{severity_hex}"><b>{severity}</b></font>',
                    styles["cell_center"],
                ),
            ]
        )

    return rows


def _issues_table(issues: list[Issue], styles: dict[str, ParagraphStyle]) -> Table:
    """Create the top issues table."""

    rows = _issue_rows(issues, styles)
    table = Table(rows, colWidths=[1.55 * inch, 2.05 * inch, 0.65 * inch, 0.8 * inch], repeatRows=1)

    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B7B7B7")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ALIGN", (2, 1), (2, -1), "CENTER"),
                ("ALIGN", (3, 1), (3, -1), "CENTER"),
            ]
        )
    )

    if len(rows) == 2 and rows[1][0].getPlainText() == "No issues found":
        table.setStyle(
            TableStyle(
                [
                    ("SPAN", (0, 1), (-1, 1)),
                    ("ALIGN", (0, 1), (-1, 1), "CENTER"),
                ]
            )
        )

    return table


def _page_decorations(canvas, doc) -> None:
    """Draw a subtle footer and separator line on each page."""

    canvas.saveState()
    width, height = doc.pagesize
    canvas.setStrokeColor(colors.HexColor("#D9D9D9"))
    canvas.setLineWidth(0.6)
    canvas.line(doc.leftMargin, height - 0.5 * inch, width - doc.rightMargin, height - 0.5 * inch)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawString(doc.leftMargin, 0.35 * inch, "Live Data Quality Monitor")
    canvas.drawRightString(width - doc.rightMargin, 0.35 * inch, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def generate_pdf_report(
    df: pd.DataFrame,
    issues: list[Issue],
    score_result: dict[str, Any],
    output_path: str | Path,
) -> Path:
    """Create a concise PDF summary and save it to disk."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    styles = _build_styles()
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.7 * inch,
    )

    report_title = (
        "Data Quality Report"
        if str(score_result.get("analysis_mode")) == "generic"
        else "Open Food Facts Data Quality Report"
    )

    elements: list[Any] = [
        Paragraph(report_title, styles["title"]),
        Paragraph(
            f"Generated: {generated_at} &nbsp;&nbsp;|&nbsp;&nbsp; Rows analyzed: {len(df)}",
            styles["meta"],
        ),
        Spacer(1, 0.12 * inch),
        _summary_table(score_result, styles),
        Spacer(1, 0.15 * inch),
        Paragraph("Score Breakdown", styles["section"]),
        _subscore_table(score_result, styles),
        Spacer(1, 0.15 * inch),
        Paragraph("Top 10 Issues", styles["section"]),
        Paragraph(
            "Only the most significant issues are shown below. The Excel workbook includes the complete detail.",
            styles["meta"],
        ),
        Spacer(1, 0.08 * inch),
        _issues_table(issues, styles),
    ]

    doc.build(elements, onFirstPage=_page_decorations, onLaterPages=_page_decorations)
    return output_path
