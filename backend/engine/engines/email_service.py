# ruff: noqa: E501
"""Email service for TetherDust report delivery.

Reads SMTP configuration from SystemConfiguration and sends report emails
with an HTML preview table and CSV attachment.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from html import escape
from typing import TYPE_CHECKING, cast

from django.core.mail import EmailMessage, get_connection

from engine.services import SystemConfigService, get

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from django.core.mail.backends.base import BaseEmailBackend

    from ..models import ReportExecution


def get_smtp_config() -> dict[str, object] | None:
    """Read SMTP settings from SystemConfiguration.

    Returns a dict with host/port/username/password/use_tls/from_email,
    or None if SMTP is not configured (smtp_host missing).
    """
    from ..models import decrypt_value

    host = get(SystemConfigService).get_value("smtp_host", "")
    if not host:
        return None

    encrypted_password = get(SystemConfigService).get_value("smtp_password", "")

    return {
        "host": host,
        "port": get(SystemConfigService).get_value("smtp_port", 587),
        "username": get(SystemConfigService).get_value("smtp_username", ""),
        "password": decrypt_value(encrypted_password) if encrypted_password else "",
        "use_tls": get(SystemConfigService).get_value("smtp_use_tls", True),
        "from_email": get(SystemConfigService).get_value("smtp_from_email", ""),
    }


def is_smtp_configured() -> bool:
    """Return True if SMTP host is set in SystemConfiguration."""

    return bool(get(SystemConfigService).get_value("smtp_host", ""))


def get_email_connection(config: dict[str, object] | None = None) -> BaseEmailBackend | None:
    """Return an SMTP email backend connection using admin-configured settings."""
    if config is None:
        config = get_smtp_config()
    if not config:
        return None

    return cast(
        "BaseEmailBackend",
        get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=config["host"],
            port=config["port"],
            username=config["username"],
            password=config["password"],
            use_tls=config["use_tls"],
        ),
    )


def _build_html_body(
    report_name: str, execution: ReportExecution, column_names: list[str], rows: list[list[object]]
) -> str:
    """Build an HTML email body with a preview of the report data."""
    preview_rows = rows[:10]
    timestamp = execution.completed_at or execution.started_at
    row_count = execution.row_count or len(rows)

    html = f"""<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto;">
    <h2 style="color: #333; margin-bottom: 4px;">{escape(report_name)}</h2>
    <p style="color: #666; font-size: 14px; margin-top: 0;">
        {escape(timestamp.strftime("%Y-%m-%d %H:%M UTC") if timestamp else "N/A")}
        &nbsp;&middot;&nbsp; {row_count} row{"s" if row_count != 1 else ""}
        {f" &nbsp;&middot;&nbsp; {execution.execution_time_ms}ms" if execution.execution_time_ms else ""}
    </p>"""

    if not column_names or not preview_rows:
        html += "<p style='color: #666;'>This report returned no data.</p>"
    else:
        html += """<table style="border-collapse: collapse; width: 100%; font-size: 13px; margin-top: 12px;">
        <thead><tr>"""
        for col in column_names:
            html += f'<th style="border: 1px solid #ddd; padding: 8px 10px; background: #f5f5f5; text-align: left; font-weight: 600;">{escape(col)}</th>'  # noqa: E501
        html += "</tr></thead><tbody>"

        for row in preview_rows:
            html += "<tr>"
            for val in row:
                display = "NULL" if val is None else escape(str(val))
                style = "border: 1px solid #ddd; padding: 6px 10px;"
                if val is None:
                    style += " color: #999; font-style: italic;"
                html += f'<td style="{style}">{display}</td>'
            html += "</tr>"
        html += "</tbody></table>"

        if row_count > 10:
            html += f'<p style="color: #666; font-size: 13px; margin-top: 8px;">Showing first 10 of {row_count} rows. Full data is attached as CSV.</p>'  # noqa: E501

    html += """<hr style="border: none; border-top: 1px solid #eee; margin-top: 24px;">
    <p style="color: #999; font-size: 12px;">Sent by TetherDust</p>
</div>"""
    return html


def _build_csv_attachment(
    report_name: str, column_names: list[str], rows: list[list[object]], max_rows: int | None = None
) -> bytes:
    """Build a CSV file as bytes for email attachment."""

    if max_rows is None:
        max_rows = get(SystemConfigService).get_value("email_max_rows", 10000)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(column_names)
    writer.writerows(rows[:max_rows])
    return buf.getvalue().encode("utf-8")


def send_report_email(execution_id: str, recipients: list[str]) -> bool:
    """Send a report execution's results as an email.

    Args:
        execution_id: ReportExecution PK
        recipients: list of email addresses

    Returns:
        True if sent successfully, False otherwise.
    """
    from ..models import ReportExecution
    from .result_storage import load_meta, load_rows

    config = get_smtp_config()
    if not config:
        logger.warning("Cannot send report email: SMTP not configured.")
        return False

    if not recipients:
        logger.info("No recipients for report email (execution %s), skipping.", execution_id)
        return False

    try:
        execution = ReportExecution.objects.select_related("definition").get(pk=execution_id)
    except ReportExecution.DoesNotExist:
        logger.warning("Report execution %s not found, cannot send email.", execution_id)
        return False

    report = execution.definition

    # Load results
    meta = load_meta(execution.pk)
    column_names = meta["column_names"] if meta else []
    rows = load_rows(execution.pk) if meta else []

    # Build email
    subject = f"Report: {report.name}"
    html_body = _build_html_body(report.name, execution, column_names, rows)

    connection = get_email_connection(config)
    if not connection:
        logger.error("Failed to create email connection.")
        return False

    try:
        email = EmailMessage(
            subject=subject,
            body=html_body,
            from_email=str(config["from_email"]) or str(config["username"]),
            to=recipients,
            connection=connection,
        )
        email.content_subtype = "html"

        # Attach CSV if there's data
        if column_names and rows:
            safe_name = re.sub(r"[^\w\-]", "_", report.name)
            csv_bytes = _build_csv_attachment(report.name, column_names, rows)
            email.attach(f"{safe_name}.csv", csv_bytes, "text/csv")

        email.send()
        logger.info(
            "Report email sent: '%s' (execution %d) to %s",
            report.name,
            execution_id,
            ", ".join(recipients),
        )
        return True

    except Exception:
        logger.exception("Failed to send report email for execution %d.", execution_id)
        return False
    finally:
        try:
            connection.close()
        except Exception:
            pass
