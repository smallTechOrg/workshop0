"""Phase 13: saved searches CRUD (slice M1 implements)."""

from __future__ import annotations

from sqlalchemy.orm import Session

LIMIT = 10


def list_for(session: Session, user_id: int) -> list[dict]:
    raise NotImplementedError


def create(session: Session, user_id: int, body: dict) -> dict:
    raise NotImplementedError


def update(session: Session, user_id: int, search_id: int, body: dict) -> dict:
    raise NotImplementedError


def delete(session: Session, user_id: int, search_id: int) -> None:
    raise NotImplementedError
