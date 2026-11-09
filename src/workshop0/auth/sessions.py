"""Opaque cookie sessions (256-bit token, SHA-256 hash in `auth_session`, 30-day expiry).

spec/architecture.md §Network identity · spec/data-model.md §auth_session. The raw token
lives only in the `workshop0_session` cookie; the DB holds its SHA-256 hex. Nothing outside
`src/workshop0/auth/` reads `auth_session`.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.workshop0.db.models import AppUser, AuthSession

SESSION_COOKIE = "workshop0_session"
SESSION_LIFETIME = timedelta(days=30)
SESSION_MAX_AGE_S = int(SESSION_LIFETIME.total_seconds())
TOUCH_INTERVAL = timedelta(minutes=5)  # ≤1 effective last_seen_at write per 5 min
USER_AGENT_MAX = 300


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(session: Session, user_id: int, *, user_agent: str | None = None) -> str:
    """Insert an `auth_session` row and return the raw cookie token (never stored)."""
    token = secrets.token_urlsafe(32)
    now = _now()
    session.add(
        AuthSession(
            token_hash=hash_token(token),
            user_id=user_id,
            created_at=now,
            expires_at=now + SESSION_LIFETIME,
            last_seen_at=now,
            user_agent=(user_agent or None) and user_agent[:USER_AGENT_MAX],
        )
    )
    session.flush()
    return token


def resolve(session: Session, token: str | None) -> AppUser | None:
    """The user behind a live (unexpired, unrevoked) session token, or None.

    Touches `last_seen_at` with a conditional UPDATE so a burst of requests costs at most
    one effective write per TOUCH_INTERVAL."""
    if not token:
        return None
    now = _now()
    row = session.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if row is None or row.revoked_at is not None or _as_utc(row.expires_at) <= now:
        return None
    user = session.get(AppUser, row.user_id)
    if user is None:
        return None
    session.execute(
        update(AuthSession)
        .where(AuthSession.id == row.id, AuthSession.last_seen_at < now - TOUCH_INTERVAL)
        .values(last_seen_at=now)
        .execution_options(synchronize_session=False)
    )
    return user


def revoke(session: Session, token: str | None) -> bool:
    """Revoke one session (sign-out). Idempotent; returns True when a live row was revoked."""
    if not token:
        return False
    result = session.execute(
        update(AuthSession)
        .where(AuthSession.token_hash == hash_token(token), AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now())
        .execution_options(synchronize_session=False)
    )
    return (result.rowcount or 0) > 0


def revoke_all_for_user(session: Session, user_id: int) -> int:
    """Revoke every live session of a user; returns the number revoked."""
    result = session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now())
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0
