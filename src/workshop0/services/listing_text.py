"""Phase 13: shared listing text for mail (slice A1 implements)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.workshop0.db.models import Opportunity


def listing_fields(session: Session, opportunity: Opportunity, base_url: str) -> dict:
    """Return {title, partner, compensation, cities, url}."""
    raise NotImplementedError
