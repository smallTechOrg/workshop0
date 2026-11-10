"""Phase 13: weekly digest (slice D1 implements)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session


def iso_week_label(now: datetime) -> str:
    raise NotImplementedError


def run_weekly(session: Session, *, now: datetime, base_url: str) -> dict:
    raise NotImplementedError
