"""
Provider-agnostic email sending.

Swap providers by changing SMTP_* env vars only (Resend, Mailgun, Gmail, your
own server all expose SMTP). If email isn't configured, we log instead of
sending so development never breaks.
"""
import logging
from email.message import EmailMessage

import aiosmtplib

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger("email")


class EmailSender:
    async def send(
        self, to: str, subject: str, html: str, text: str | None = None
    ) -> None:
        raise NotImplementedError


class SMTPEmailSender(EmailSender):
    async def send(self, to, subject, html, text=None):
        msg = EmailMessage()
        msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text or "Please view this email in an HTML-capable client.")
        msg.add_alternative(html, subtype="html")

        # 465 → implicit SSL; 587 → STARTTLS. Never both.
        use_ssl = settings.smtp_ssl
        start_tls = False if use_ssl else settings.smtp_tls

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            use_tls=use_ssl,
            start_tls=start_tls,
        )


class ConsoleEmailSender(EmailSender):
    async def send(self, to, subject, html, text=None):
        logger.warning(
            "[email disabled] would send to=%s subject=%r (set EMAIL_ENABLED + SMTP_* to enable)",
            to,
            subject,
        )


def _sender() -> EmailSender:
    if settings.email_enabled and settings.smtp_host and settings.smtp_user:
        return SMTPEmailSender()
    return ConsoleEmailSender()


async def send_email(
    to: str, subject: str, html: str, text: str | None = None
) -> bool:
    """Best-effort send. Never raises — returns True/False."""
    try:
        await _sender().send(to, subject, html, text)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("Email send failed: %s", exc)
        return False
