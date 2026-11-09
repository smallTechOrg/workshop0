"""The only identity surface product code may import (spec/architecture.md §Network identity).

Interface stub laid down by the Phase-11 shared scaffold; slice S1 (auth) fills the bodies
and keeps these signatures.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request


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


def current_user(request: Request) -> CurrentUser | None:
    """The signed-in user for this request, or None (never raises for a missing session)."""
    raise NotImplementedError


def require_user(request: Request) -> CurrentUser:
    """401 `not_signed_in` without a session; on non-GET also 403 `csrf_failed` without the header."""
    raise NotImplementedError


def require_admin(request: Request) -> AdminActor:
    """A valid `X-Admin-Key` or a session whose user is an admin; else 401/403."""
    raise NotImplementedError
