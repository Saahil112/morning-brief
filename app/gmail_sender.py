"""Gmail sender — sends the digest email via SMTP using a Google App Password.

Requires only two env-vars: GMAIL_SENDER and GMAIL_APP_PASSWORD.
No OAuth consent screen, no token refresh, no extra dependencies.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import GMAIL_APP_PASSWORD, GMAIL_RECIPIENT, GMAIL_SENDER
from app.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def send_email(subject: str, html_body: str) -> None:
    """
    Send an HTML email through Gmail SMTP.

    Parameters
    ----------
    subject : str
        Email subject line.
    html_body : str
        Full HTML content of the email.
    """
    with tracer.start_as_current_span("send_email") as span:
        span.set_attribute("email.recipient", GMAIL_RECIPIENT)
        span.set_attribute("email.subject", subject)

        message = MIMEMultipart("alternative")
        message["From"] = GMAIL_SENDER
        message["To"] = GMAIL_RECIPIENT
        message["Subject"] = subject

        # Plain-text fallback
        message.attach(
            MIMEText("Please view this email in an HTML-capable client.", "plain")
        )
        message.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.send_message(message)

        logger.info("Email sent via SMTP to %s", GMAIL_RECIPIENT)
        span.set_attribute("email.status", "sent")
