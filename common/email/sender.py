"""SMTP email sender used by all agents."""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class EmailSender:
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_pass: str,
        default_to: str,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_pass = smtp_pass
        self.default_to = default_to

    def send(self, subject: str, html_body: str, plain_body: str, to_email: str | None = None) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.smtp_user
            msg["To"] = to_email or self.default_to
            msg["Subject"] = subject

            msg.attach(MIMEText(plain_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)

            return True
        except Exception as exc:
            print(f"✗ Failed to send email: {exc}")
            return False

