"""
Gmail sender — sends the digest email via the Gmail API using OAuth 2.0.

Expects a *token.json* (refresh-token) created once via the OAuth consent
flow and a *credentials.json* (OAuth client secret downloaded from the
Google Cloud Console).  Both paths are configurable in config.py.
"""

from __future__ import annotations

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.config import (
    GMAIL_CLIENT_ID,
    GMAIL_CLIENT_SECRET,
    GMAIL_CREDENTIALS_JSON,
    GMAIL_RECIPIENT,
    GMAIL_REFRESH_TOKEN,
    GMAIL_SENDER,
    GMAIL_TOKEN_JSON,
)
from app.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _get_credentials() -> Credentials:
    """Load or refresh Gmail OAuth credentials.

    On Cloud Run the three env-vars GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET
    and GMAIL_REFRESH_TOKEN are used directly (no files needed).
    Locally it falls back to credentials.json / token.json files.
    """
    creds: Credentials | None = None

    # ── Path 1: build from env vars (Cloud Run) ─────────────────────────
    if GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET and GMAIL_REFRESH_TOKEN:
        creds = Credentials(
            token=None,
            refresh_token=GMAIL_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GMAIL_CLIENT_ID,
            client_secret=GMAIL_CLIENT_SECRET,
            scopes=SCOPES,
        )
        creds.refresh(Request())
        logger.info("Gmail credentials built from env vars")
        return creds

    # ── Path 2: file-based (local dev) ──────────────────────────────────
    token_path = Path(GMAIL_TOKEN_JSON)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                GMAIL_CREDENTIALS_JSON, SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Persist for next run
        token_path.write_text(creds.to_json())

    return creds


def send_email(subject: str, html_body: str) -> dict:
    """
    Send an HTML email through the Gmail API.

    Parameters
    ----------
    subject : str
        Email subject line.
    html_body : str
        Full HTML content of the email.

    Returns
    -------
    dict
        Gmail API response (contains 'id', 'threadId', 'labelIds').
    """
    with tracer.start_as_current_span("send_email") as span:
        span.set_attribute("email.recipient", GMAIL_RECIPIENT)
        span.set_attribute("email.subject", subject)

        creds = _get_credentials()
        service = build("gmail", "v1", credentials=creds)

        message = MIMEMultipart("alternative")
        message["From"] = GMAIL_SENDER
        message["To"] = GMAIL_RECIPIENT
        message["Subject"] = subject

        # Plain-text fallback
        message.attach(
            MIMEText("Please view this email in an HTML-capable client.", "plain")
        )
        message.attach(MIMEText(html_body, "html"))

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        body = {"raw": raw}

        result = service.users().messages().send(userId="me", body=body).execute()
        span.set_attribute("email.message_id", result.get("id", ""))
        logger.info("Email sent: Message ID: %s", result.get("id"))
        return result
