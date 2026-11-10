"""Phase 13: saved-search criteria and alert enqueue (slice A1 implements)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.workshop0.db.models import Opportunity


def validate_criteria(session: Session, criteria: dict) -> dict:
    raise NotImplementedError


def matches(criteria: dict, opportunity: Opportunity, topic_slugs: frozenset[str]) -> bool:
    raise NotImplementedError


def enqueue_alerts_for(session: Session, opportunity: Opportunity, *, base_url: str) -> int:
    raise NotImplementedError
