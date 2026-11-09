"""Admin network invites (spec/api.md §Phase 11 Admin pool → invites; data-model.md
§network_invite).

An invite is a single-use, 14-day link `/invite/<token>` for one email address. Accepting
it (signing in with the same email) is S1's callback; this module only creates and lists.
Phase 11 shows the URL for copying — email sending arrives in Phase 12.
"""

from __future__ import annotations

import math
import re
import secrets
from datetime import datetime, timedelta

import structlog
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.workshop0.api._common import as_utc, iso_z, utcnow
from src.workshop0.db.models import NetworkInvite
from src.workshop0.services.audit import record_action

log = structlog.get_logger("workshop0")

INVITE_LIFETIME = timedelta(days=14)
EMAIL_MAX = 254
NAME_MAX = 120
ADMIN_ACTOR = "admin"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InviteCreate(BaseModel):
    email: str
    name: str | None = None

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        cleaned = (value or "").strip().lower()
        if not cleaned or len(cleaned) > EMAIL_MAX or not _EMAIL_RE.match(cleaned):
            raise ValueError("enter a valid email address")
        return cleaned

    @field_validator("name")
    @classmethod
    def _valid_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) > NAME_MAX:
            raise ValueError(f"must be at most {NAME_MAX} characters")
        return cleaned


def invite_url(base_url: str, token: str) -> str:
    return f"{base_url}/invite/{token}"


def invite_status(invite: NetworkInvite, now: datetime) -> str:
    """`accepted` once used; else `expired` past `expires_at`; else `pending`."""
    if invite.accepted_at is not None:
        return "accepted"
    if as_utc(invite.expires_at) <= now:
        return "expired"
    return "pending"


def serialize_invite(invite: NetworkInvite, base_url: str, now: datetime) -> dict:
    return {
        "id": invite.id,
        "email": invite.email,
        "name": invite.name,
        "url": invite_url(base_url, invite.token),
        "status": invite_status(invite, now),
        "created_by": invite.created_by,
        "created_at": iso_z(invite.created_at),
        "expires_at": iso_z(invite.expires_at),
        "accepted_at": iso_z(invite.accepted_at) if invite.accepted_at is not None else None,
    }


def create_invite(session: Session, body: InviteCreate, *, by: str, base_url: str) -> dict:
    now = utcnow()
    invite = NetworkInvite(
        token=secrets.token_urlsafe(32),
        email=body.email,
        name=body.name,
        created_by=by,
        created_at=now,
        expires_at=now + INVITE_LIFETIME,
    )
    session.add(invite)
    session.flush()
    record_action(
        session,
        None,
        ADMIN_ACTOR,
        "invite.create",
        {"email": invite.email, "name": invite.name, "by": by},
        subject_type="invite",
        subject_id=invite.id,
    )
    session.commit()
    log.info("network.invite_created", invite_id=invite.id)
    return serialize_invite(invite, base_url, now)


def list_invites(session: Session, *, base_url: str, page: int, page_size: int) -> dict:
    now = utcnow()
    total = int(session.scalar(select(func.count(NetworkInvite.id))) or 0)
    rows = session.scalars(
        select(NetworkInvite)
        .order_by(NetworkInvite.created_at.desc(), NetworkInvite.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "invites": [serialize_invite(row, base_url, now) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }
