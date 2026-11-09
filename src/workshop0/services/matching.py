"""Rule-based matching (STUB in Phase 12 Wave A; filled by slice B2). Interface: agent.md."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.workshop0.db.models import Opportunity, TrainerProfile


@dataclass(frozen=True)
class Candidate:
    profile: TrainerProfile
    rule_score: float


@dataclass(frozen=True)
class Match:
    opportunity: Opportunity
    rule_score: float
    invited: bool


def rule_score(profile: TrainerProfile, opportunity: Opportunity) -> float:
    raise NotImplementedError("filled by slice B2")


def eligible(session: Session, opportunity: Opportunity, *, include_budget: bool = True) -> list[Candidate]:
    raise NotImplementedError("filled by slice B2")


def matches_for(session: Session, profile: TrainerProfile, limit: int = 10) -> list[Match]:
    raise NotImplementedError("filled by slice B2")
