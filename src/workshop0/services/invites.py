"""Network invites (spec/api.md §Phase 11 → Invite acceptance, §Phase 11d; data-model.md
§network_invite).

An invite is a single-use, 14-day link `/invite/<token>` for one email address. This module
owns the whole lifecycle: create (re-using a pending invite for the same email), list,
revoke, the derived status, and the ONE acceptance check (`check_invite`) + write
(`accept_invite`) shared by the OIDC callback and `POST /api/me/invite/accept`.
Phase 11 shows the URL for copying — email sending arrives in Phase 12.
"""

from __future__ import annotations

import math
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from fastapi import HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.workshop0.api._common import api_error, as_utc, iso_z, utcnow
from src.workshop0.auth.deps import CurrentUser
from src.workshop0.db.models import AppUser, NetworkInvite, TrainerProfile
from src.workshop0.services.audit import record_action
from src.workshop0.services.workshops import mask_email

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


def _accepted_emails(session: Session, emails: set[str]) -> set[str]:
    """The subset of `emails` that has at least one accepted invite."""
    if not emails:
        return set()
    return set(
        session.scalars(
            select(NetworkInvite.email)
            .where(NetworkInvite.email.in_(sorted(emails)), NetworkInvite.accepted_at.is_not(None))
            .distinct()
        )
    )


def invite_status(invite: NetworkInvite, now: datetime, *, sibling_accepted: bool = False) -> str:
    """Derived status, first match wins (data-model.md §network_invite → Status):
    revoked → accepted → superseded (a sibling invite for the same email is accepted) →
    expired → pending. Only `pending` is actionable."""
    if invite.revoked_at is not None:
        return "revoked"
    if invite.accepted_at is not None:
        return "accepted"
    if sibling_accepted:
        return "superseded"
    if as_utc(invite.expires_at) <= now:
        return "expired"
    return "pending"


def serialize_invite(invite: NetworkInvite, base_url: str, now: datetime, status: str) -> dict:
    return {
        "id": invite.id,
        "email": invite.email,
        "name": invite.name,
        "url": invite_url(base_url, invite.token),
        "status": status,
        "created_by": invite.created_by,
        "created_at": iso_z(invite.created_at),
        "expires_at": iso_z(invite.expires_at),
        "accepted_at": iso_z(invite.accepted_at) if invite.accepted_at is not None else None,
        "revoked_at": iso_z(invite.revoked_at) if invite.revoked_at is not None else None,
        "revoked_by": invite.revoked_by,
    }


def create_invite(
    session: Session, body: InviteCreate, *, by: str, base_url: str
) -> tuple[dict, bool]:
    """Create — or re-use the email's pending invite (api.md §Phase 11d). Returns
    `(payload, reused)`. 409 `invite_already_accepted` when the email already joined."""
    now = utcnow()
    if _accepted_emails(session, {body.email}):
        raise api_error(
            "invite_already_accepted", "This email has already joined through an invite.", 409
        )
    candidates = session.scalars(
        select(NetworkInvite)
        .where(
            NetworkInvite.email == body.email,
            NetworkInvite.revoked_at.is_(None),
            NetworkInvite.accepted_at.is_(None),
            NetworkInvite.expires_at > now,
        )
        .order_by(NetworkInvite.created_at.desc(), NetworkInvite.id.desc())
        .with_for_update()
    ).all()
    if candidates:
        invite = candidates[0]
        invite.expires_at = now + INVITE_LIFETIME
        if body.name:
            invite.name = body.name
        record_action(
            session,
            None,
            ADMIN_ACTOR,
            "invite.refresh",
            {"email": invite.email, "name": invite.name, "by": by},
            subject_type="invite",
            subject_id=invite.id,
        )
        session.commit()
        log.info("network.invite_refreshed", invite_id=invite.id)
        return serialize_invite(invite, base_url, now, "pending"), True

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
    return serialize_invite(invite, base_url, now, "pending"), False


def revoke_invite(session: Session, invite_id: int, *, by: str, base_url: str) -> dict:
    """pending / expired / superseded → revoked (+ audit `invite.revoke`); already revoked →
    the same payload, no write; accepted → 409 `invite_not_revocable`; unknown → 404."""
    invite = session.scalar(
        select(NetworkInvite).where(NetworkInvite.id == invite_id).with_for_update()
    )
    if invite is None:
        raise api_error("not_found", "No invite with that id.", 404)
    now = utcnow()
    if invite.revoked_at is not None:
        return serialize_invite(invite, base_url, now, "revoked")
    if invite.accepted_at is not None:
        raise api_error("invite_not_revocable", "An accepted invite can't be revoked.", 409)
    invite.revoked_at = now
    invite.revoked_by = by
    record_action(
        session,
        None,
        ADMIN_ACTOR,
        "invite.revoke",
        {"email": invite.email, "by": by},
        subject_type="invite",
        subject_id=invite.id,
    )
    session.commit()
    log.info("network.invite_revoked", invite_id=invite.id)
    return serialize_invite(invite, base_url, now, "revoked")


def list_invites(session: Session, *, base_url: str, page: int, page_size: int) -> dict:
    now = utcnow()
    total = int(session.scalar(select(func.count(NetworkInvite.id))) or 0)
    rows = list(
        session.scalars(
            select(NetworkInvite)
            .order_by(NetworkInvite.created_at.desc(), NetworkInvite.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    accepted = _accepted_emails(session, {row.email for row in rows})
    return {
        "invites": [
            serialize_invite(
                row,
                base_url,
                now,
                invite_status(row, now, sibling_accepted=row.email in accepted),
            )
            for row in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


# --------------------------------------------------------------------------- acceptance


class InviteRefused(Exception):
    """A refusal from `check_invite`: `code` is the api.md error code; `extra` carries the
    masked invite email for `invite_email_mismatch`."""

    def __init__(self, code: str, extra: dict | None = None):
        super().__init__(code)
        self.code = code
        self.extra = extra or {}


@dataclass
class InviteMatch:
    """`check_invite`'s success: `noop` = already applied to this user (accepted by them, or
    a superseded row whose accepted sibling is theirs) — nothing to write."""

    invite: NetworkInvite
    noop: bool = False


def check_invite(
    session: Session, token: str | None, email: str, user_id: int | None
) -> InviteMatch | None:
    """The ONE acceptance check (api.md §Invite acceptance §6), run before any write.

    Ordering, first match wins: unknown → None · revoked → `invite_revoked` · accepted (this
    user: no-op; anyone else, incl. a deleted account's null: `invite_used`) · superseded
    (the sibling's acceptor: no-op; anyone else: continue) · expired → `invite_expired` ·
    email mismatch → `invite_email_mismatch` (extra `invite_email` masked) · match."""
    if token is None:
        return None
    invite = session.scalar(select(NetworkInvite).where(NetworkInvite.token == token))
    if invite is None:
        return None
    if invite.revoked_at is not None:
        raise InviteRefused("invite_revoked")
    if invite.accepted_at is not None:
        if user_id is not None and invite.accepted_user_id == user_id:
            return InviteMatch(invite, noop=True)
        raise InviteRefused("invite_used")
    if user_id is not None:
        sibling = session.scalar(
            select(NetworkInvite.id).where(
                NetworkInvite.email == invite.email,
                NetworkInvite.id != invite.id,
                NetworkInvite.accepted_at.is_not(None),
                NetworkInvite.accepted_user_id == user_id,
            )
        )
        if sibling is not None:
            return InviteMatch(invite, noop=True)
    if as_utc(invite.expires_at) <= utcnow():
        raise InviteRefused("invite_expired")
    invite_email = invite.email.strip().lower()
    if invite_email != email.strip().lower():
        raise InviteRefused("invite_email_mismatch", {"invite_email": mask_email(invite_email)})
    return InviteMatch(invite)


def accept_invite(session: Session, match: InviteMatch, user: AppUser | CurrentUser) -> bool:
    """Step 4's writes: stamp the invite, verify an EXISTING unverified profile (the one
    profile write allowed outside `/api/me`: `verified*` only) + audit `trainer.verify`.
    A no-op match writes nothing. Returns whether a profile was verified now. The caller
    commits and logs `auth.invite_accepted`."""
    if match.noop:
        return False
    invite = match.invite
    now = utcnow()
    if invite.accepted_at is None:
        invite.accepted_at = now
        invite.accepted_user_id = user.id
    profile = session.scalar(select(TrainerProfile).where(TrainerProfile.user_id == user.id))
    if profile is None or profile.verified:
        return False
    profile.verified = True
    profile.verified_at = now
    profile.verified_by = invite.created_by
    record_action(
        session,
        None,
        "user",
        "trainer.verify",
        {"via": "invite", "invite_id": invite.id},
        subject_type="trainer",
        subject_id=profile.id,
    )
    return True


_REFUSAL_HTTP = {
    "invite_revoked": (410, "This invite has been withdrawn — ask smallTech for a new one."),
    "invite_used": (409, "This invite has already been used."),
    "invite_expired": (410, "This invite has expired — ask smallTech for a new one."),
}


def accept_for_user(session: Session, token: str | None, user: CurrentUser) -> dict:
    """`POST /api/me/invite/accept`: the callback's checks with the SESSION user's email.
    Never creates a user or a session."""
    try:
        match = check_invite(session, token, user.email, user.id)
    except InviteRefused as exc:
        log.warning("auth.invite_refused", code=exc.code, user_id=user.id)
        if exc.code == "invite_email_mismatch":
            masked = exc.extra["invite_email"]
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "invite_email_mismatch",
                    "message": f"This invite was sent to {masked} — sign in with that Google account.",
                    "details": {"invite_email": masked},
                },
            ) from exc
        status, message = _REFUSAL_HTTP[exc.code]
        raise api_error(exc.code, message, status) from exc
    if match is None:
        raise api_error("invite_not_found", "This invite link isn't valid.", 404)
    if match.noop:
        return {"invite_accepted": True, "profile_verified": False}
    profile_verified = accept_invite(session, match, user)
    session.commit()
    log.info(
        "auth.invite_accepted",
        invite_id=match.invite.id,
        user_id=user.id,
        profile_verified=profile_verified,
        email=mask_email(user.email),
    )
    return {"invite_accepted": True, "profile_verified": profile_verified}
