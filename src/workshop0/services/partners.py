"""Managed partner list — spec/api.md §Phase 11b. Stub; F2 fills the bodies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:  # Partner model lands in F1
    from src.workshop0.db.models import Partner

PARTNER_EXISTS_MESSAGE: str = "A partner with this name already exists."


def normalize_name(name: str) -> tuple[str, str]:
    """Return `(collapsed, name_key)`."""
    raise NotImplementedError


def partner_ref(partner: Partner) -> dict:
    """Return `{"id", "internal_name", "display_name", "active"}`."""
    raise NotImplementedError


def active_partners(session: Session) -> list[Partner]:
    raise NotImplementedError


def resolve_partner(
    session: Session,
    *,
    partner_id: int | None,
    partner_id_given: bool,
    internal_name: str | None,
    internal_name_given: bool,
    display_name_hint: str | None,
    current_partner_id: int | None,
    by: str,
) -> Partner | None:
    """Flushes but never commits. Rules: api.md §Phase 11b."""
    raise NotImplementedError
