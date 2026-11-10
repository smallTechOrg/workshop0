"""Shortlist ranker (spec/agent.md §Shortlist ranker).

Deterministic prefilter + rule score (`services/matching.py`) -> the top 40 candidates go to one
structured-output Anthropic call -> deterministic guardrails -> `match_suggestion` rows.
Any `LLMUnavailable` / `LLMError` falls back to the top 10 by rule score (`ranked_by="rules"`).
Candidate text (headlines, past-work titles) is untrusted: it is delimited as data, and only
ids from the candidate set are ever accepted from the model.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.workshop0.ai import anthropic_client
from src.workshop0.ai.anthropic_client import LLMError, LLMResult, LLMUnavailable
from src.workshop0.ai.usage import record_usage
from src.workshop0.db.models import MatchSuggestion, Opportunity, OpportunityTopic, Topic, TrainerTopic
from src.workshop0.services import matching
from src.workshop0.services.matching import Candidate
from src.workshop0.services import locations as loc

log = structlog.get_logger("workshop0")

PURPOSE = "shortlist_rank"
TOOL_NAME = "submit_shortlist"
MAX_TOKENS = 2048
TIMEOUT_S = 30.0
CANDIDATE_CAP = 40
TOP_N = 10
REASON_MAX = 300
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BLOCK_TAGS = re.compile(r"<\s*/?\s*(listing|candidates)\s*>", re.IGNORECASE)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ranking": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "profile_id": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["profile_id", "reason"],
            },
        }
    },
    "required": ["ranking"],
}


@dataclass
class ShortlistRun:
    run_id: str
    ranked_by: str  # "ai" | "rules"
    suggestions: list[dict] = field(default_factory=list)  # {rank, profile_id, rule_score, reason}
    cost_usd: Decimal = Decimal("0")


@lru_cache(maxsize=None)
def _prompt(name: str) -> str:
    return (_PROMPTS_DIR / f"shortlist_rank_{name}.md").read_text(encoding="utf-8")


def _render(template: str, values: dict[str, str]) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), template)


def _clean(text: str | None, limit: int) -> str:
    cleaned = _CONTROL_CHARS.sub(" ", text or "")
    cleaned = _BLOCK_TAGS.sub("[tag]", cleaned)
    return " ".join(cleaned.split())[:limit]


def _candidate_summaries(session: Session, opp: Opportunity, candidates: list[Candidate]) -> list[dict]:
    ids = [c.profile.id for c in candidates]
    slugs = {t.id: t.slug for t in session.scalars(select(Topic))}
    levels: dict[int, list[str]] = {pid: [] for pid in ids}
    for profile_id, topic_id, level in session.execute(
        select(TrainerTopic.profile_id, TrainerTopic.topic_id, TrainerTopic.level).where(
            TrainerTopic.profile_id.in_(ids)
        )
    ):
        levels[profile_id].append(f"{slugs.get(topic_id, topic_id)}:{level}")
    fits = matching.rate_fits(session, opp, ids)
    out = []
    for c in candidates:
        p = c.profile
        try:
            past = json.loads(p.past_work_json or "[]")
        except ValueError:
            past = []
        titles = [_clean(w.get("title"), 80) for w in past if isinstance(w, dict) and w.get("title")][:5]
        out.append(
            {
                "id": p.id,
                "headline": _clean(p.headline, 160),
                "topics": sorted(levels[p.id]),
                "city": _clean(p.city, 80) or None,
                "remote_ok": bool(p.remote_ok),
                "verified": bool(p.verified),
                "past_work": titles,
                "rate_fits": fits.get(p.id, True),
            }
        )
    return out


def _listing_summary(session: Session, opp: Opportunity) -> dict:
    topic_rows = session.scalars(
        select(Topic.slug)
        .join(OpportunityTopic, OpportunityTopic.topic_id == Topic.id)
        .where(OpportunityTopic.opportunity_id == opp.id)
    ).all()
    cities = [i["city"] for i in loc.parse_stored(opp.locations_json, opp.city, opp.location_mode)]
    return {
        "title": _clean(opp.title, 160),
        "type": opp.type,
        "summary": _clean(opp.summary, 280),
        "description": _clean(opp.description_md, 1500),
        "topics": sorted(topic_rows),
        "location_mode": opp.location_mode,
        "cities": cities,
        "min_level": opp.min_level,
        "starts_on": opp.starts_on.isoformat() if opp.starts_on else None,
        "ends_on": opp.ends_on.isoformat() if opp.ends_on else None,
    }


def guard_ranking(content: Any, candidates: list[Candidate]) -> list[dict]:
    """Guardrails (agent.md step 3). Returns `[{profile_id, reason}]` with reasons possibly None
    only for the rule-score top-up entries."""
    by_id = {c.profile.id: c for c in candidates}
    target = min(TOP_N, len(candidates))
    chosen: list[dict] = []
    seen: set[int] = set()
    entries = content.get("ranking") if isinstance(content, dict) else None
    for entry in entries if isinstance(entries, list) else []:
        if len(chosen) >= TOP_N:
            break
        if not isinstance(entry, dict):
            continue
        pid, reason = entry.get("profile_id"), entry.get("reason")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid not in by_id or pid in seen:
            continue
        reason = _CONTROL_CHARS.sub(" ", reason).strip()[:REASON_MAX].strip() if isinstance(reason, str) else ""
        if not reason:
            continue
        seen.add(pid)
        chosen.append({"profile_id": pid, "reason": reason})
    for c in candidates:  # already best-rule-score first
        if len(chosen) >= target:
            break
        if c.profile.id not in seen:
            seen.add(c.profile.id)
            chosen.append({"profile_id": c.profile.id, "reason": None})
    return chosen


def new_run_id() -> str:
    return secrets.token_urlsafe(16)  # 22 chars


def run_shortlist(session: Session, opportunity_id: int) -> ShortlistRun:
    """Run the ranker for one listing; flushes `match_suggestion` (+ `ai_usage`) rows, never commits."""
    opp = session.get(Opportunity, opportunity_id)
    if opp is None:
        raise LookupError(f"no opportunity {opportunity_id}")
    candidates = matching.eligible(session, opp)[:CANDIDATE_CAP]
    scores = {c.profile.id: round(c.rule_score, 3) for c in candidates}  # match_suggestion.rule_score is Numeric(6,3)
    ranked_by = "rules"
    picks = [{"profile_id": c.profile.id, "reason": None} for c in candidates[:TOP_N]]
    llm: LLMResult | None = None

    if candidates and anthropic_client.is_available():
        from src.workshop0.config.settings import get_settings

        user = _render(
            _prompt("user"),
            {
                "listing": json.dumps(_listing_summary(session, opp), ensure_ascii=False),
                "candidates": "\n".join(
                    json.dumps(s, ensure_ascii=False) for s in _candidate_summaries(session, opp, candidates)
                ),
            },
        )
        try:
            llm = anthropic_client.call_json(
                system=_prompt("system"),
                user=user,
                tool_name=TOOL_NAME,
                input_schema=INPUT_SCHEMA,
                model=get_settings().workshop0_ai_network_model,
                max_tokens=MAX_TOKENS,
                timeout_s=TIMEOUT_S,
            )
            picks = guard_ranking(llm.content, candidates)
            ranked_by = "ai"
        except (LLMUnavailable, LLMError) as exc:
            log.error(
                "ai.call_failed",
                purpose=PURPOSE,
                opportunity_id=opportunity_id,
                cause=getattr(exc, "cause", "unavailable"),
                status=getattr(exc, "status", None),
                request_id=getattr(exc, "request_id", None),
            )
            llm = None

    run_id = new_run_id()
    suggestions: list[dict] = []
    for rank, pick in enumerate(picks, start=1):
        pid = pick["profile_id"]
        session.add(
            MatchSuggestion(
                opportunity_id=opportunity_id,
                profile_id=pid,
                run_id=run_id,
                rank=rank,
                rule_score=scores[pid],
                reason=pick["reason"],
                ranked_by=ranked_by,
            )
        )
        suggestions.append({"rank": rank, "profile_id": pid, "rule_score": scores[pid], "reason": pick["reason"]})
    cost = Decimal("0")
    if llm is not None:
        row = record_usage(session, llm, purpose=PURPOSE, opportunity_id=opportunity_id)
        session.refresh(row)
        cost = Decimal(str(row.cost_usd))
    session.flush()
    log.info(
        "shortlist.run",
        opportunity_id=opportunity_id,
        run_id=run_id,
        ranked_by=ranked_by,
        candidates=len(candidates),
        suggestions=len(suggestions),
    )
    return ShortlistRun(run_id=run_id, ranked_by=ranked_by, suggestions=suggestions, cost_usd=cost)
