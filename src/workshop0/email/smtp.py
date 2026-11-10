"""SMTP transport (stdlib smtplib, STARTTLS). The password is never logged or put in errors."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from src.workshop0.config.settings import Settings
from src.workshop0.email.render import Rendered


def build_message(settings: Settings, to: str, rendered: Rendered) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.resolved_smtp_from
    msg["To"] = to
    msg["Subject"] = rendered.subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain="workshop0")
    msg.set_content(rendered.text)
    msg.add_alternative(rendered.html, subtype="html")
    return msg


def send(settings: Settings, to: str, rendered: Rendered) -> None:
    msg = build_message(settings, to, rendered)
    with smtplib.SMTP(settings.workshop0_smtp_host, settings.workshop0_smtp_port, timeout=15) as s:
        if settings.workshop0_smtp_starttls:
            s.starttls()
        if settings.workshop0_smtp_user and settings.workshop0_smtp_password.get_secret_value():
            s.login(settings.workshop0_smtp_user, settings.workshop0_smtp_password.get_secret_value())
        s.send_message(msg)


def safe_error(exc: Exception, settings: Settings) -> str:
    """`ExcType: message`, with the password scrubbed, capped at 500 chars."""
    text = f"{type(exc).__name__}: {exc}"
    secret = settings.workshop0_smtp_password.get_secret_value()
    if secret:
        text = text.replace(secret, "***")
    return text[:500]
