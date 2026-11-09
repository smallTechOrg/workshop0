"""The only identity surface product code may import (spec/architecture.md §Network identity).

- `current_user(request) -> CurrentUser | None` — never raises for a missing session.
- `require_user` — 401 `not_signed_in`; on a mutation also 403 `csrf_failed` without
  `X-Requested-With: workshop0`.
- `require_admin` — a valid `X-Admin-Key` (unchanged behaviour) **or** a session whose user
  is an admin (`email_verified` and email in `WORKSHOP0_ADMIN_EMAILS`, evaluated on every
  request, so de-listing revokes on the next request). Returns `AdminActor`.

All three are plain `(request)` callables, usable directly or via `Depends(...)`.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from src.workshop0.api._common import api_error
from src.workshop0.config.settings import Settings, get_settings
from src.workshop0.security import admin_key_matches

CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "workshop0"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
ADMIN_KEY_ACTOR = "admin-key"

_STATE_USER = "workshop0_current_user"
_UNSET = object()


@dataclass(frozen=True)
class CurrentUser:
    id: int
    email: str
    display_name: str | None
    avatar_url: str | None
    is_admin: bool


@dataclass(frozen=True)
class AdminActor:
    """Who passed the admin gate: `"admin-key"` or the admin's email."""

    by: str


def admin_emails(settings: Settings | None = None) -> frozenset[str]:
    raw = (settings or get_settings()).workshop0_admin_emails
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())


def is_admin_email(email: str, email_verified: bool, settings: Settings | None = None) -> bool:
    return bool(email_verified) and email.strip().lower() in admin_emails(settings)


def _load_user(token: str | None) -> CurrentUser | None:
    if not token:
        return None
    from src.workshop0.auth import sessions
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        user = sessions.resolve(session, token)
        if user is None:
            return None
        return CurrentUser(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
            is_admin=is_admin_email(user.email, user.email_verified),
        )


def current_user(request: Request) -> CurrentUser | None:
    """The signed-in user for this request, or None (never raises for a missing session)."""
    cached = getattr(request.state, _STATE_USER, _UNSET)
    if cached is not _UNSET:
        return cached
    from src.workshop0.auth.sessions import SESSION_COOKIE

    user = _load_user(request.cookies.get(SESSION_COOKIE))
    setattr(request.state, _STATE_USER, user)
    return user


def check_csrf(request: Request) -> None:
    """Cookie-authenticated mutations must carry `X-Requested-With: workshop0`."""
    if request.method.upper() in SAFE_METHODS:
        return
    if request.headers.get(CSRF_HEADER, "").strip().lower() != CSRF_VALUE:
        raise api_error(
            "csrf_failed",
            "This request is missing the X-Requested-With: workshop0 header — reload the page and try again.",
            403,
        )


def require_user(request: Request) -> CurrentUser:
    """401 `not_signed_in` without a session; on non-GET also 403 `csrf_failed` without the header."""
    user = current_user(request)
    if user is None:
        raise api_error("not_signed_in", "Sign in to continue.", 401)
    check_csrf(request)
    return user


def require_admin(request: Request) -> AdminActor:
    """A valid `X-Admin-Key` or a session whose user is an admin; else 401/403."""
    # An empty / whitespace-only `X-Admin-Key` (the existing frontend always sends the header,
    # empty for a session admin) counts as absent, so the session is consulted.
    provided_key = request.headers.get("X-Admin-Key")
    if provided_key is not None and not provided_key.strip():
        provided_key = None
    if admin_key_matches(provided_key, get_settings().resolved_admin_key):
        actor = AdminActor(by=ADMIN_KEY_ACTOR)
    else:
        user = current_user(request)
        if user is not None and user.is_admin:
            check_csrf(request)
            actor = AdminActor(by=user.email)
        elif user is not None and not provided_key:
            raise api_error(
                "not_admin",
                "This account isn't an admin on this server — sign in with an admin account or use the access key.",
                403,
            )
        else:
            # Byte-for-byte the pre-Phase-11 key failure.
            raise api_error(
                "invalid_admin_key",
                "The access key is missing or does not match this server's WORKSHOP0_ADMIN_KEY.",
                401,
            )
    request.state.admin_actor = actor
    return actor
