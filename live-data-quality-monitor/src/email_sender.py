"""Send the generated reports by email."""

from __future__ import annotations

import mimetypes
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

Issue = dict[str, Any]
logger = logging.getLogger(__name__)
UNAVAILABLE_MESSAGE = (
    "Email delivery isn't available in this environment right now because of a temporary issue. "
    "You can still download the Excel and PDF reports above."
)


def _load_dotenv() -> None:
    """Load environment variables from the project .env file."""

    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError(
            "python-dotenv is required. Install dependencies with "
            "`pip install -r requirements.txt`."
        ) from exc

    load_dotenv(ENV_PATH)


def _load_secret_values() -> dict[str, str]:
    """Read email settings from Streamlit secrets when available."""

    try:
        import streamlit as st  # type: ignore
    except ImportError:
        return {}

    try:
        secrets = st.secrets
    except Exception:
        return {}

    values: dict[str, str] = {}
    direct_keys = ("EMAIL_ADDRESS", "EMAIL_PASSWORD", "SMTP_SERVER", "SMTP_PORT")
    for key in direct_keys:
        try:
            value = secrets[key]
        except Exception:
            value = None
        if value:
            values[key] = str(value).strip()

    try:
        email_block = secrets.get("email", {})
    except Exception:
        email_block = {}

    if isinstance(email_block, dict):
        mapping = {
            "EMAIL_ADDRESS": ("address", "email_address"),
            "EMAIL_PASSWORD": ("password",),
            "SMTP_SERVER": ("server", "smtp_server"),
            "SMTP_PORT": ("port", "smtp_port"),
        }
        for env_key, candidates in mapping.items():
            if env_key in values:
                continue
            for candidate in candidates:
                if candidate in email_block and email_block[candidate]:
                    values[env_key] = str(email_block[candidate]).strip()
                    break

    return values


def _load_email_settings() -> dict[str, Any]:
    """Load SMTP credentials from environment variables or Streamlit secrets."""

    _load_dotenv()
    settings = {
        "EMAIL_ADDRESS": os.getenv("EMAIL_ADDRESS", "").strip(),
        "EMAIL_PASSWORD": os.getenv("EMAIL_PASSWORD", ""),
        "SMTP_SERVER": os.getenv("SMTP_SERVER", "").strip(),
        "SMTP_PORT": os.getenv("SMTP_PORT", "0").strip(),
    }

    secret_values = _load_secret_values()
    for key, value in secret_values.items():
        if value:
            settings[key] = value

    missing = [key for key, value in settings.items() if not value]
    if missing:
        raise RuntimeError(
            "Email credentials are not configured. Set EMAIL_ADDRESS, EMAIL_PASSWORD, "
            "SMTP_SERVER, and SMTP_PORT in .env or Streamlit secrets."
        )

    try:
        settings["SMTP_PORT"] = int(str(settings["SMTP_PORT"]))
    except ValueError as exc:
        raise RuntimeError("SMTP_PORT must be an integer value.") from exc

    return settings


def is_email_configured() -> bool:
    """Return True when the email credentials are available."""

    try:
        _load_email_settings()
    except RuntimeError:
        return False
    return True


def _validate_recipient_email(recipient_email: str) -> str:
    """Perform a light sanity check on the destination email address."""

    parsed = parseaddr(recipient_email)[1].strip()
    if not parsed or parsed != recipient_email.strip() or "@" not in parsed:
        raise ValueError("Please enter a valid recipient email address.")
    return parsed


def _sort_issues(issues: list[Issue]) -> list[Issue]:
    """Sort issues by severity and count for email summaries."""

    severity_order = {"Critical": 0, "Warning": 1, "Info": 2}
    return sorted(
        issues,
        key=lambda issue: (
            severity_order.get(str(issue.get("severity")), 99),
            -int(issue.get("count", 0)),
            str(issue.get("column", "")),
        ),
    )


def _build_subject(score_result: dict[str, Any]) -> str:
    """Create the email subject based on the validation status."""

    status = str(score_result.get("status", "Warning"))
    overall_score = float(score_result.get("overall_score", 0.0))
    if status == "Excellent":
        return f"Data Quality Report \u2014 {status}"
    return f"Data Quality Alert \u2014 {status}, Score: {overall_score:.1f}%"


def _build_body(
    score_result: dict[str, Any],
    issues: list[Issue] | None = None,
) -> str:
    """Write a short business-friendly summary for the email body."""

    status = str(score_result.get("status", "Warning"))
    overall_score = float(score_result.get("overall_score", 0.0))
    completeness = float(score_result.get("completeness", 0.0))
    validity = float(score_result.get("validity", 0.0))
    uniqueness = float(score_result.get("uniqueness", 0.0))
    consistency = float(score_result.get("consistency", 0.0))

    lines = [
        "Hello,",
        "",
        "The latest data quality validation run is attached.",
        f"Overall score: {overall_score:.1f}% ({status}).",
        (
            "Score breakdown: "
            f"completeness {completeness:.1f}%, "
            f"validity {validity:.1f}%, "
            f"uniqueness {uniqueness:.1f}%, "
            f"consistency {consistency:.1f}%."
        ),
    ]

    if issues:
        top_issues = _sort_issues(issues)[:3]
        if top_issues:
            issue_lines = []
            for issue in top_issues:
                column = str(issue.get("column", "")).replace("__row__", "duplicate rows")
                issue_type = str(issue.get("issue_type", "")).replace("_", " ")
                count = int(issue.get("count", 0))
                issue_lines.append(f"{column} - {issue_type} ({count} records)")

            lines.extend(
                [
                    "",
                    "Main items affecting the result: " + "; ".join(issue_lines) + ".",
                ]
            )

    lines.extend(
        [
            "",
            "The attached Excel workbook contains the full breakdown, and the PDF provides a concise summary for quick review.",
            "",
            "Regards,",
            "Live Data Quality Monitor",
        ]
    )
    return "\n".join(lines)


def _attachment_type(path: Path) -> tuple[str, str]:
    """Return a safe MIME type for the requested attachment."""

    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type:
        return ("application", "octet-stream")
    maintype, subtype = mime_type.split("/", 1)
    return maintype, subtype


def send_report_email(
    recipient_email: str,
    score_result: dict[str, Any],
    excel_path: str | Path,
    pdf_path: str | Path,
    issues: list[Issue] | None = None,
) -> dict[str, Any]:
    """Send the Excel and PDF reports to the requested recipient.

    The function returns a result dictionary so callers can show a friendly
    success or failure message without handling exceptions themselves.
    """

    try:
        recipient = _validate_recipient_email(recipient_email)
        settings = _load_email_settings()
        excel_file = Path(excel_path)
        pdf_file = Path(pdf_path)

        if not excel_file.exists():
            raise FileNotFoundError(f"Excel report not found: {excel_file}")
        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF report not found: {pdf_file}")

        message = EmailMessage()
        message["From"] = settings["EMAIL_ADDRESS"]
        message["To"] = recipient
        message["Subject"] = _build_subject(score_result)
        message.set_content(_build_body(score_result, issues=issues))

        for attachment_path in (excel_file, pdf_file):
            maintype, subtype = _attachment_type(attachment_path)
            message.add_attachment(
                attachment_path.read_bytes(),
                maintype=maintype,
                subtype=subtype,
                filename=attachment_path.name,
            )

        smtp_server = str(settings["SMTP_SERVER"])
        smtp_port = int(settings["SMTP_PORT"])
        smtp_password = str(settings["EMAIL_PASSWORD"])
        smtp_user = str(settings["EMAIL_ADDRESS"])

        context = ssl.create_default_context()
        if smtp_port == 465:
            server: smtplib.SMTP | smtplib.SMTP_SSL = smtplib.SMTP_SSL(
                smtp_server,
                smtp_port,
                context=context,
                timeout=20,
            )
        else:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=20)

        with server:
            server.ehlo()
            if smtp_port != 465:
                server.starttls(context=context)
                server.ehlo()
            server.login(smtp_user, smtp_password)
            server.send_message(message)

        return {
            "success": True,
            "message": f"Email sent successfully to {recipient}.",
            "subject": message["Subject"],
        }
    except ValueError as exc:
        logger.info("Email delivery was not sent because the recipient address was invalid.")
        return {"success": False, "message": str(exc)}
    except smtplib.SMTPAuthenticationError as exc:
        logger.exception("SMTP authentication failed while sending the report email.")
        return {
            "success": False,
            "message": UNAVAILABLE_MESSAGE,
        }
    except (FileNotFoundError, RuntimeError, smtplib.SMTPException, OSError) as exc:
        logger.exception("Email delivery failed while preparing or sending the report.")
        return {"success": False, "message": UNAVAILABLE_MESSAGE}
    except Exception as exc:
        logger.exception("Unexpected email delivery failure.")
        return {"success": False, "message": UNAVAILABLE_MESSAGE}
