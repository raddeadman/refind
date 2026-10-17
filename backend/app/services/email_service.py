"""Outgoing email. In development MailHog catches everything (localhost:8025)."""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from ..config import get_settings

log = logging.getLogger(__name__)


def _send(to: str, subject: str, body: str) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.send_message(message)


async def send(to: str, subject: str, body: str) -> bool:
    """Returns False instead of raising: a mail outage must not break sign-up
    (the user can ask for the link again)."""
    try:
        await asyncio.to_thread(_send, to, subject, body)
        return True
    except OSError as exc:
        log.warning("Could not send email to %s: %s", to, exc)
        return False


async def send_verification(to: str, name: str, token: str) -> bool:
    link = f"{get_settings().frontend_url}/verify-email?token={token}"
    body = (
        f"Hi {name},\n\n"
        "Confirm your ReFind account by opening this link (valid for 24 hours):\n\n"
        f"{link}\n\n"
        "If you did not create an account, ignore this email.\n"
    )
    return await send(to, "Verify your ReFind account", body)
