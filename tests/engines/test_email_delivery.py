"""End-to-end SMTP delivery: a real socket server, the real Django SMTP backend.

Complements ``test_email_service.py`` (which covers config assembly and the send
guards without opening a socket) by driving ``send_report_email`` all the way to
the wire, so the assembled message — subject, HTML body, CSV attachment and
envelope — is asserted as the bytes an MTA would actually receive.
"""

from __future__ import annotations

import logging
import socket
import threading
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.django_db


class _SMTPServer(threading.Thread):
    """Minimal one-shot SMTP sink that records the DATA payload."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.payload = ""
        self.envelope: list[str] = []

    def run(self) -> None:
        conn, _ = self.sock.accept()
        f = conn.makefile("rwb")
        conn.sendall(b"220 localhost ESMTP test\r\n")
        in_data = False
        lines: list[str] = []
        while True:
            line = f.readline()
            if not line:
                break
            text = line.decode("utf-8", "replace").rstrip("\r\n")
            if in_data:
                if text == ".":
                    in_data = False
                    self.payload = "\n".join(lines)
                    conn.sendall(b"250 OK queued\r\n")
                    continue
                lines.append(text)
                continue
            upper = text.upper()
            if upper.startswith("EHLO") or upper.startswith("HELO"):
                conn.sendall(b"250-localhost\r\n250 AUTH LOGIN PLAIN\r\n")
            elif upper.startswith(("MAIL FROM", "RCPT TO")):
                self.envelope.append(text)
                conn.sendall(b"250 OK\r\n")
            elif upper.startswith("DATA"):
                in_data = True
                conn.sendall(b"354 End data with <CR><LF>.<CR><LF>\r\n")
            elif upper.startswith("QUIT"):
                conn.sendall(b"221 Bye\r\n")
                break
            else:
                conn.sendall(b"250 OK\r\n")
        conn.close()


def test_report_email_delivers_html_and_csv(
    tmp_path: Path, settings: Any, caplog: pytest.LogCaptureFixture
) -> None:
    settings.TETHERDUST_REPORT_RESULTS_DIR = tmp_path

    from engine.engines import email_service
    from engine.engines.result_storage import save_results
    from engine.models import ReportDefinition, ReportExecution
    from engine.services import SystemConfigService, get
    from model_bakery import baker

    server = _SMTPServer()
    server.start()

    cfg = get(SystemConfigService)
    cfg.set_value("smtp_host", "127.0.0.1")
    cfg.set_value("smtp_port", server.port, "integer")
    cfg.set_value("smtp_use_tls", False, "boolean")
    cfg.set_value("smtp_from_email", "reports@example.com")

    report = ReportDefinition.objects.create(
        database=baker.make("engine.DatabaseConnection"),
        name="Live Mail Check",
        sql_query="SELECT 1",
        schedule_type="manual",
        delivery_method="email",
        delivery_config={"email_recipients": ["ops@example.com"]},
    )
    execution = ReportExecution.objects.create(
        definition=report, status="success", row_count=2, execution_time_ms=12
    )
    save_results(execution.pk, ["id", "name"], [[1, "alpha"], [2, None]])

    with caplog.at_level(logging.INFO, logger="engine.engines.email_service"):
        sent = email_service.send_report_email(execution.pk, ["ops@example.com"])
    server.join(timeout=5)

    assert sent is True, "send_report_email returned False"
    assert any("ops@example.com" in line for line in server.envelope)
    assert "Subject: Report: Live Mail Check" in server.payload
    assert "Live_Mail_Check.csv" in server.payload
    assert "alpha" in server.payload
    # The confirmation line interpolates a `rex_…` string id; a `%d` placeholder
    # here would blow up in the handler instead of logging the send.
    assert any("Report email sent" in r.getMessage() for r in caplog.records)
