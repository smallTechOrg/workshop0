"""Phase 13: public trainer directory (slice R1 implements)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from src.workshop0.db.models import AppUser, TrainerProfile

MIN_COMPLETENESS = 60


def public_path(slug: str) -> str:
    return "/trainers/" + slug


def ensure_slug(session: Session, profile: TrainerProfile, user: AppUser) -> str:
    raise NotImplementedError


def list_public(session: Session, *, topic: str | None, page: int, base_url: str) -> dict:
    raise NotImplementedError


def get_public(session: Session, slug: str, *, base_url: str) -> dict | None:
    raise NotImplementedError


def sitemap_entries(session: Session, base_url: str) -> list[tuple[str, datetime]]:
    raise NotImplementedError
