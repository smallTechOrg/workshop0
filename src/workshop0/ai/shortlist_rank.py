"""Shortlist ranker (STUB in Phase 12 Wave A; filled by slice B2). Interface: agent.md."""

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session


@dataclass
class ShortlistRun:
    run_id: str
    ranked_by: str  # "ai" | "rules"
    suggestions: list[dict] = field(default_factory=list)  # {rank, profile_id, rule_score, reason}
    cost_usd: Decimal = Decimal("0")


def run_shortlist(session: Session, opportunity_id: int) -> ShortlistRun:
    raise NotImplementedError("filled by slice B2")
