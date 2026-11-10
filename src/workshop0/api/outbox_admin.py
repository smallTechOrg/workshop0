"""`/api/admin/outbox` - list rows, retry failed ones. A page load also drains (self-healing)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.workshop0.api._common import api_error, iso_z, ok
from src.workshop0.config.settings import get_settings
from src.workshop0.db.models import EmailOutbox
from src.workshop0.db.session import get_session
from src.workshop0.email import sender
from src.workshop0.security import require_admin_key

router = APIRouter(prefix="/api/admin/outbox", dependencies=[Depends(require_admin_key)])

STATUSES = ("queued", "sent", "recorded", "failed")
PAGE_SIZE = 25


def _row(r: EmailOutbox) -> dict:
    return {
        "id": r.id,
        "to": r.to_email,
        "template": r.template,
        "subject": r.subject,
        "status": r.status,
        "attempts": r.attempts,
        "last_error": r.last_error,
        "created_at": iso_z(r.created_at),
        "sent_at": iso_z(r.sent_at) if r.sent_at is not None else None,
    }


@router.get("")
def list_outbox(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    session: Session = Depends(get_session),
) -> dict:
    if status is not None and status not in STATUSES:
        raise api_error("validation_error", "status must be queued, sent, recorded or failed.", 422)
    sender.drain()  # self-heal anything left queued by a restart
    session.expire_all()
    query = select(EmailOutbox)
    count = select(func.count()).select_from(EmailOutbox)
    if status:
        query = query.where(EmailOutbox.status == status)
        count = count.where(EmailOutbox.status == status)
    total = session.scalar(count) or 0
    rows = session.scalars(
        query.order_by(EmailOutbox.created_at.desc(), EmailOutbox.id.desc())
        .limit(PAGE_SIZE)
        .offset((page - 1) * PAGE_SIZE)
    ).all()
    return ok(
        {
            "items": [_row(r) for r in rows],
            "page": page,
            "page_size": PAGE_SIZE,
            "total": total,
            "smtp_configured": get_settings().smtp_configured,
        }
    )


@router.post("/{outbox_id}/retry")
def retry(outbox_id: int, session: Session = Depends(get_session)) -> dict:
    row = session.scalar(select(EmailOutbox).where(EmailOutbox.id == outbox_id).with_for_update())
    if row is None:
        raise api_error("not_found", "No outbox row with that id.", 404)
    if row.status != "failed":
        raise api_error("not_retryable", "Only failed rows can be retried.", 409)
    row.status = "queued"
    row.attempts = 0
    row.last_error = None
    session.commit()
    sender.drain()
    session.expire_all()
    session.refresh(row)
    return ok({"outbox": _row(row)})
