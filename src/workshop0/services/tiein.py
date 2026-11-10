"""Phase 13: workshop <-> trainer facilitator links (slice T1 implements)."""

from __future__ import annotations

from sqlalchemy.orm import Session

ROLES = ("lead", "co", "ta")


def list_for_workshop(session: Session, workshop_id: int) -> list[dict]:
    raise NotImplementedError


def replace_for_workshop(session: Session, workshop_id: int, items: list, *, by: str) -> list[dict]:
    raise NotImplementedError


def add_one(session: Session, workshop_id: int, profile_id: int, role: str, *, by: str) -> list[dict]:
    raise NotImplementedError


def workshops_for(session: Session, profile_id: int, *, base_url: str) -> list[dict]:
    raise NotImplementedError
