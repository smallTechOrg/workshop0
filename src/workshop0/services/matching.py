"""Rule-based matching (spec/agent.md §Shortlist ranker, step 1).

Deterministic and DB-light: a listing's eligible trainers (prefilter), the 0-1 rule score,
`matches_for` (Matched for you) and the admin-pool rule filters. Nothing here calls an LLM.

All filtering is done in Python over eagerly batch-loaded rows (hundreds of trainers, tens of
listings - the Phase-11 scale target), so the behaviour is identical on every database dialect.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from src.workshop0.api._common import utcnow
from src.workshop0.db.models import (
    CvDocument,
    Opportunity,
    OpportunityInvite,
    OpportunityTopic,
    Topic,
    TrainerProfile,
    TrainerTopic,
)
from src.workshop0.services import locations as loc
from src.workshop0.services import profiles
from src.workshop0.services.opportunities import effective_status

LEVEL_RANK = {"intermediate": 1, "advanced": 2, "expert": 3}
LEVEL_WEIGHT = {"intermediate": 0.6, "advanced": 0.8, "expert": 1.0}
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
LOCATION_MODES = ("remote", "onsite", "hybrid")
BUDGET_UNITS = ("hour", "day", "course", "month")
BUDGET_CURRENCIES = ("INR", "USD")
MAX_SPAN_DAYS = 7  # a span of a week or more covers every weekday


@dataclass(frozen=True)
class Candidate:
    profile: TrainerProfile
    rule_score: float


@dataclass(frozen=True)
class Match:
    opportunity: Opportunity
    rule_score: float
    invited: bool


# --------------------------------------------------------------------------- contexts


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


@dataclass
class _ProfileCtx:
    profile: TrainerProfile
    levels: dict[int, str] = field(default_factory=dict)  # topic_id -> level
    topic_count: int = 0
    has_cv: bool = False
    city_key: str = ""
    available_days: set[str] = field(default_factory=set)
    blackouts: list[tuple[date, date]] = field(default_factory=list)

    def completeness_fraction(self) -> float:
        pct = profiles.completeness(self.profile, topic_count=self.topic_count, has_cv=self.has_cv).pct
        return pct / 100.0


def _profile_contexts(session: Session, rows: list[TrainerProfile]) -> list[_ProfileCtx]:
    if not rows:
        return []
    ids = [p.id for p in rows]
    levels: dict[int, dict[int, str]] = {pid: {} for pid in ids}
    for profile_id, topic_id, level in session.execute(
        select(TrainerTopic.profile_id, TrainerTopic.topic_id, TrainerTopic.level).where(
            TrainerTopic.profile_id.in_(ids)
        )
    ):
        levels[profile_id][topic_id] = level
    user_ids = [p.user_id for p in rows]
    cv_users = set(session.scalars(select(CvDocument.user_id).where(CvDocument.user_id.in_(user_ids))))
    out: list[_ProfileCtx] = []
    for p in rows:
        availability = _loads(p.availability_json, {})
        days = {
            d
            for d, slots in (availability.items() if isinstance(availability, dict) else [])
            if d in WEEKDAYS and slots
        }
        blackouts: list[tuple[date, date]] = []
        for item in _loads(p.blackout_json, []):
            if isinstance(item, dict):
                start, end = _as_date(item.get("start")), _as_date(item.get("end"))
                if start and end:
                    blackouts.append((start, max(start, end)))
        out.append(
            _ProfileCtx(
                profile=p,
                levels=levels[p.id],
                topic_count=len(levels[p.id]),
                has_cv=p.user_id in cv_users,
                city_key=loc.collapse(p.city or "").casefold(),
                available_days=days,
                blackouts=blackouts,
            )
        )
    return out


@dataclass
class _OppCtx:
    opportunity: Opportunity
    topic_ids: list[int]
    cities: set[str]
    start: date | None
    end: date | None
    weekdays: set[str]
    budget: tuple[int, str, str] | None  # (max, currency, unit)

    @property
    def min_rank(self) -> int:
        return LEVEL_RANK.get(self.opportunity.min_level or "", 0)


def _budget_of(opp: Opportunity) -> tuple[int, str, str] | None:
    """Admin budget first; otherwise the public compensation as the budget."""
    if opp.budget_max is not None and opp.budget_currency and opp.budget_unit:
        return (opp.budget_max, opp.budget_currency, opp.budget_unit)
    if opp.budget_max is None and opp.compensation_max is not None and opp.compensation_currency and opp.compensation_unit:
        return (opp.compensation_max, opp.compensation_currency, opp.compensation_unit)
    return None


def _weekdays_between(start: date, end: date) -> set[str]:
    span = min((end - start).days, MAX_SPAN_DAYS - 1)
    return {WEEKDAYS[(start + timedelta(days=i)).weekday()] for i in range(span + 1)}


def _opp_contexts(session: Session, opps: list[Opportunity]) -> list[_OppCtx]:
    if not opps:
        return []
    by_opp: dict[int, list[int]] = {o.id: [] for o in opps}
    for opportunity_id, topic_id in session.execute(
        select(OpportunityTopic.opportunity_id, OpportunityTopic.topic_id)
        .where(OpportunityTopic.opportunity_id.in_(list(by_opp)))
        .order_by(OpportunityTopic.topic_id)
    ):
        by_opp[opportunity_id].append(topic_id)
    out: list[_OppCtx] = []
    for o in opps:
        cities = {
            loc.collapse(i["city"]).casefold()
            for i in loc.parse_stored(o.locations_json, o.city, o.location_mode)
        }
        start = o.starts_on or o.ends_on
        end = o.ends_on or o.starts_on
        if start and end and end < start:
            start, end = end, start
        out.append(
            _OppCtx(
                opportunity=o,
                topic_ids=by_opp[o.id],
                cities=cities,
                start=start,
                end=end,
                weekdays=_weekdays_between(start, end) if start and end else set(),
                budget=_budget_of(o),
            )
        )
    return out


# --------------------------------------------------------------------------- the rules


def _topic_ok(p: _ProfileCtx, o: _OppCtx) -> bool:
    if not o.topic_ids:
        return True
    return any(LEVEL_RANK.get(p.levels.get(t, ""), 0) >= max(o.min_rank, 1) for t in o.topic_ids)


def _dates_ok(p: _ProfileCtx, o: _OppCtx) -> bool:
    if o.start is None or o.end is None:
        return True
    if p.profile.available_from is not None and p.profile.available_from > o.start:
        return False
    return not any(b_start <= o.end and o.start <= b_end for b_start, b_end in p.blackouts)


def _rate_ok(p: _ProfileCtx, o: _OppCtx) -> bool:
    if o.budget is None:
        return True
    budget_max, currency, unit = o.budget
    prof = p.profile
    if prof.pro_bono:
        return True
    return (
        prof.rate_min is not None
        and prof.rate_currency == currency
        and prof.rate_unit == unit
        and prof.rate_min <= budget_max
    )


def _location_ok(p: _ProfileCtx, o: _OppCtx) -> bool:
    mode = o.opportunity.location_mode
    if mode == "remote" or not o.cities:
        return True
    same_city = bool(p.city_key) and p.city_key in o.cities
    if mode == "onsite":
        return same_city
    return same_city or bool(p.profile.remote_ok)  # hybrid


def _passes(p: _ProfileCtx, o: _OppCtx, *, include_budget: bool) -> bool:
    return (
        _topic_ok(p, o)
        and _dates_ok(p, o)
        and _location_ok(p, o)
        and (not include_budget or _rate_ok(p, o))
    )


def _score(p: _ProfileCtx, o: _OppCtx) -> float:
    if o.topic_ids:
        coverage = sum(LEVEL_WEIGHT.get(p.levels.get(t, ""), 0.0) for t in o.topic_ids) / len(o.topic_ids)
    else:
        coverage = 0.0
    overlap = (
        len(o.weekdays & p.available_days) / len(o.weekdays) if o.weekdays else 1.0
    )
    total = (
        0.5 * coverage
        + 0.2 * (1.0 if p.profile.verified else 0.0)
        + 0.15 * p.completeness_fraction()
        + 0.15 * overlap
    )
    return round(total, 6)


def _order_key(c: Candidate) -> tuple:
    updated = c.profile.updated_at
    stamp = updated.timestamp() if isinstance(updated, datetime) else 0.0
    return (-c.rule_score, -stamp, c.profile.id)


# --------------------------------------------------------------------------- public API


def rule_score(profile: TrainerProfile, opportunity: Opportunity) -> float:
    """0-1 score of `profile` against `opportunity` (no prefilter)."""
    session = object_session(profile)
    if session is None:
        raise ValueError("rule_score() needs an attached profile")
    (p,) = _profile_contexts(session, [profile])
    (o,) = _opp_contexts(session, [opportunity])
    return _score(p, o)


def eligible(session: Session, opportunity: Opportunity, *, include_budget: bool = True) -> list[Candidate]:
    """Profiles passing the prefilter, best rule score first (ties: updated_at desc, id)."""
    (o,) = _opp_contexts(session, [opportunity])
    rows = list(session.scalars(select(TrainerProfile)))
    out = [
        Candidate(profile=p.profile, rule_score=_score(p, o))
        for p in _profile_contexts(session, rows)
        if _passes(p, o, include_budget=include_budget)
    ]
    out.sort(key=_order_key)
    return out


def rate_fits(session: Session, opportunity: Opportunity, profile_ids: list[int]) -> dict[int, bool]:
    """Per-profile budget fit (True for everyone when the listing has no budget)."""
    (o,) = _opp_contexts(session, [opportunity])
    rows = list(session.scalars(select(TrainerProfile).where(TrainerProfile.id.in_(profile_ids))))
    return {p.profile.id: _rate_ok(p, o) for p in _profile_contexts(session, rows)}


def invited_profile_ids(session: Session, opportunity_id: int) -> set[int]:
    return set(
        session.scalars(
            select(OpportunityInvite.profile_id).where(OpportunityInvite.opportunity_id == opportunity_id)
        )
    )


def matches_for(session: Session, profile: TrainerProfile, limit: int = 10) -> list[Match]:
    """Effective-open listings ranked by rule score for `profile`; invited listings first.

    The prefilter is the shortlist's without the admin-only budget step. An explicit admin
    invite is shown even when the prefilter would drop the listing."""
    now = utcnow()
    open_listings = [
        o
        for o in session.scalars(select(Opportunity).where(Opportunity.status == "open"))
        if effective_status(o, now) == "open"
    ]
    if not open_listings:
        return []
    invited = set(
        session.scalars(select(OpportunityInvite.opportunity_id).where(OpportunityInvite.profile_id == profile.id))
    )
    (p,) = _profile_contexts(session, [profile])
    matches: list[Match] = []
    for o in _opp_contexts(session, open_listings):
        is_invited = o.opportunity.id in invited
        if is_invited or _passes(p, o, include_budget=False):
            matches.append(Match(opportunity=o.opportunity, rule_score=_score(p, o), invited=is_invited))
    matches.sort(
        key=lambda m: (
            not m.invited,
            -m.rule_score,
            -(m.opportunity.published_at.timestamp() if m.opportunity.published_at else 0.0),
            m.opportunity.id,
        )
    )
    return matches[:limit]


# --------------------------------------------------------------------------- admin pool filters


def pool_filter_ids(
    session: Session,
    *,
    topics: list[str],
    min_level: str | None,
    budget_max: int | None,
    currency: str | None,
    unit: str | None,
    available_start: date | None,
    available_end: date | None,
    location_mode: str | None,
    city: str | None,
) -> set[int]:
    """Profile ids passing every supplied rule filter (api.md Phase 12, extended trainers list)."""
    slugs = {s.strip().lower() for s in topics if s and s.strip()}
    topic_ids = (
        set(session.scalars(select(Topic.id).where(Topic.slug.in_(slugs)))) if slugs else set()
    )
    city_key = loc.collapse(city or "").casefold()
    start = available_start or available_end
    end = available_end or available_start
    rows = list(session.scalars(select(TrainerProfile)))
    ids: set[int] = set()
    for p in _profile_contexts(session, rows):
        if min_level or slugs:
            need = LEVEL_RANK.get(min_level or "", 1)
            wanted = topic_ids if slugs else set(p.levels)
            if not any(LEVEL_RANK.get(p.levels.get(t, ""), 0) >= need for t in wanted):
                continue
        if budget_max is not None:
            if not (
                p.profile.pro_bono
                or (
                    p.profile.rate_min is not None
                    and p.profile.rate_min <= budget_max
                    and p.profile.rate_currency == currency
                    and p.profile.rate_unit == unit
                )
            ):
                continue
        if start and end:
            if p.profile.available_from is not None and p.profile.available_from > start:
                continue
            if any(b0 <= end and start <= b1 for b0, b1 in p.blackouts):
                continue
        if location_mode in ("onsite", "hybrid"):
            same = bool(city_key) and p.city_key == city_key
            if location_mode == "onsite" and not same:
                continue
            if location_mode == "hybrid" and not (same or p.profile.remote_ok):
                continue
        elif location_mode is None and city_key and p.city_key != city_key:
            continue
        ids.add(p.profile.id)
    return ids
