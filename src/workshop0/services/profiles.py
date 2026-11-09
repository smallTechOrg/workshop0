"""Trainer-profile domain helpers (spec/api.md §Phase 11 Completeness).

Interface stub laid down by the Phase-11 shared scaffold; filled by slice S7 (me-api).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.workshop0.db.models import TrainerProfile


@dataclass(frozen=True)
class Completeness:
    pct: int
    missing: list[str] = field(default_factory=list)


def completeness(profile: TrainerProfile) -> Completeness:
    """Ten weighted checks, 10 % each (headline, bio, topics, location, link, past work,
    rate, weekly availability, available_from, CV on file)."""
    raise NotImplementedError
