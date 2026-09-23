from __future__ import annotations

import base64
from email.message import EmailMessage


def build_gmail_draft_payload(to_email: str, subject: str, body: str) -> dict:
    """Create Gmail API-compatible draft payload (ready for users.drafts.create)."""
    message = EmailMessage()
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return {"message": {"raw": encoded}}
