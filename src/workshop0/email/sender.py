"""Outbox drain + senders (architecture.md Email). Never raises into a request."""

from __future__ import annotations

import json
from datetime import timedelta

import structlog
from fastapi import BackgroundTasks
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.workshop0.api._common import api_error, as_utc, utcnow
from src.workshop0.config.settings import get_settings
from src.workshop0.db.models import EmailOutbox, NetworkInvite
from src.workshop0.email import smtp
from src.workshop0.email.outbox import enqueue
from src.workshop0.email.render import render
from src.workshop0.services.audit import record_action

log = structlog.get_logger()

MAX_ATTEMPTS = 3
PER_RECIPIENT_PER_HOUR = 10
GLOBAL_PER_HOUR = 100


def _mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:2]}***@{domain}" if domain else f"{local[:2]}***"


def schedule_drain(background_tasks: BackgroundTasks) -> None:
    """Run `drain()` after the response is sent."""
    background_tasks.add_task(drain)


def _limit(name: str, default: int) -> int:
    value = getattr(get_settings(), name, None)
    return value if isinstance(value, int) and value > 0 else default


def _rate_limited(session: Session, to_email: str) -> bool:
    since = utcnow() - timedelta(hours=1)
    sent = EmailOutbox.status == "sent"
    per = session.scalar(
        select(func.count()).where(
            sent, EmailOutbox.sent_at >= since, func.lower(EmailOutbox.to_email) == to_email.lower()
        )
    )
    if (per or 0) >= _limit("workshop0_email_rate_per_recipient", PER_RECIPIENT_PER_HOUR):
        return True
    total = session.scalar(select(func.count()).where(sent, EmailOutbox.sent_at >= since))
    return (total or 0) >= _limit("workshop0_email_rate_global", GLOBAL_PER_HOUR)


def _process(session: Session, row: EmailOutbox) -> None:
    settings = get_settings()
    try:
        ctx = json.loads(row.context_json or "{}")
        rendered = render(row.template, ctx)
    except Exception as exc:  # bad template/context: permanent
        row.attempts = MAX_ATTEMPTS
        row.status = "failed"
        row.last_error = smtp.safe_error(exc, settings)
        log.error("email.failed", outbox_id=row.id, template=row.template, reason="render")
        return
    row.subject = rendered.subject
    if not settings.smtp_configured:
        row.status = "recorded"
        row.last_error = None
        log.info("email.recorded", outbox_id=row.id, template=row.template, to=_mask(row.to_email))
        return
    if _rate_limited(session, row.to_email):
        row.status = "recorded"
        row.last_error = "rate_limited"
        log.info(
            "email.recorded", outbox_id=row.id, template=row.template,
            to=_mask(row.to_email), reason="rate_limited",
        )
        return
    while row.attempts < MAX_ATTEMPTS:
        row.attempts += 1
        try:
            smtp.send(settings, row.to_email, rendered)
        except Exception as exc:
            row.last_error = smtp.safe_error(exc, settings)
            log.warning(
                "email.attempt_failed", outbox_id=row.id, attempt=row.attempts,
                error_type=type(exc).__name__,
            )
            continue
        row.status = "sent"
        row.sent_at = utcnow()
        row.last_error = None
        log.info("email.sent", outbox_id=row.id, template=row.template, to=_mask(row.to_email))
        return
    row.status = "failed"
    log.error("email.failed", outbox_id=row.id, template=row.template, to=_mask(row.to_email))


def drain(limit: int = 20) -> int:
    """Claim up to `limit` queued rows (SKIP LOCKED on PostgreSQL) and deliver / record them.
    Returns the number processed; swallows every error (never fails a request)."""
    from src.workshop0.db.session import create_db_session

    done = 0
    try:
        with create_db_session() as session:
            rows = session.scalars(
                select(EmailOutbox)
                .where(EmailOutbox.status == "queued")
                .order_by(EmailOutbox.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            for row in rows:
                _process(session, row)
                session.commit()  # per row: a sent mail is never re-sent after a later crash
                done += 1
    except Exception as exc:
        log.error("email.drain_error", error_type=type(exc).__name__)
    return done


def enqueue_invite_email(session: Session, invite: NetworkInvite, base_url: str) -> EmailOutbox:
    """Enqueue one `network.invite` for this invite. 409 for revoked / used / expired invites.
    Dedupe `invite:{id}:{token_prefix}`; writes audit `invite.email` once per row."""
    now = utcnow()
    if invite.revoked_at is not None:
        raise api_error("invite_revoked", "This invite was revoked.", 409)
    if invite.accepted_at is not None:
        raise api_error("invite_used", "This invite has already been used.", 409)
    if as_utc(invite.expires_at) <= now:
        raise api_error("invite_expired", "This invite has expired.", 409)
    from src.workshop0.services.invites import invite_url

    key = f"invite:{invite.id}:{invite.token[:8]}"
    existing = session.scalar(select(EmailOutbox).where(EmailOutbox.dedupe_key == key))
    row = existing or enqueue(
        session,
        to=invite.email,
        template="network.invite",
        context={
            "name": invite.name or "",
            "invite_url": invite_url(base_url.rstrip("/"), invite.token),
            "expires_at": as_utc(invite.expires_at).strftime("%Y-%m-%d"),
        },
        dedupe_key=key,
    )
    if existing is None:
        record_action(
            session, None, "admin", "invite.email",
            {"invite_id": invite.id, "to": _mask(invite.email)},
            subject_type="invite", subject_id=invite.id,
        )
        session.flush()
    return row
