"""Token generation + auth lookups per spec/architecture.md §Auth model."""

import secrets
from typing import TYPE_CHECKING

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.workshop0.api._common import api_error
from src.workshop0.config.settings import get_settings
from src.workshop0.db.models import Participant, Workshop

if TYPE_CHECKING:
    from src.workshop0.auth.deps import AdminActor


def generate_admin_token() -> str:
    return secrets.token_urlsafe(32)


def generate_participant_token() -> str:
    return secrets.token_urlsafe(16)


def generate_join_slug() -> str:
    return secrets.token_urlsafe(6)


def admin_key_matches(provided: str | None, expected: str) -> bool:
    if not provided or not expected:
        return False
    return secrets.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def require_admin_key(request: Request) -> "AdminActor":
    """FastAPI dependency for the admin surface.

    From Phase 11 it delegates to `auth.deps.require_admin`: a valid `X-Admin-Key` behaves
    exactly as before (401 `invalid_admin_key` otherwise), and a signed-in admin session
    (email in WORKSHOP0_ADMIN_EMAILS, checked per request) passes without the key."""
    from src.workshop0.auth.deps import require_admin

    return require_admin(request)


def workshop_by_admin_token(session: Session, admin_token: str) -> Workshop:
    workshop = session.scalar(select(Workshop).where(Workshop.admin_token == admin_token))
    if workshop is None:
        raise api_error("not_found", "No workshop matches this facilitator link.", 404)
    return workshop


def workshop_by_join_slug(session: Session, join_slug: str) -> Workshop:
    workshop = session.scalar(select(Workshop).where(Workshop.join_slug == join_slug))
    if workshop is None:
        raise api_error("not_found", "This workshop link isn't valid — check with your facilitator.", 404)
    return workshop


def participant_by_token(session: Session, token: str) -> tuple[Participant, Workshop]:
    participant = session.scalar(select(Participant).where(Participant.token == token))
    if participant is None:
        raise api_error("not_found", "This personal link isn't valid — re-join from the join link.", 404)
    workshop = session.get(Workshop, participant.workshop_id)
    if workshop is None:
        raise api_error("not_found", "This personal link isn't valid — re-join from the join link.", 404)
    return participant, workshop
