"""Shared 60-profile matching pool (spec/agent.md §Testing - Ranker).

`seed_pool(session)` inserts one OPEN onsite listing (cities Pune + Bengaluru, topics
generative-ai / python / kubernetes, min level advanced, budget INR 10,000 per day, dates
2027-03-01..02 = Mon..Tue) and 60 trainers. Exactly 17 pass the prefilter; each of the other 43
fails exactly one rule. The obvious best (`best_id`) is expert in all three topics, verified, in
Pune, available, in budget. Returns the PRECOMPUTED id sets the tests assert against.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.workshop0.db.models import (
    AppUser,
    Opportunity,
    OpportunityTopic,
    Topic,
    TrainerProfile,
    TrainerTopic,
)

POOL_SIZE = 60
ELIGIBLE_COUNT = 17
LISTING_TOPICS = ("generative-ai", "python", "kubernetes")
STARTS_ON = date(2027, 3, 1)  # a Monday
ENDS_ON = date(2027, 3, 2)


@dataclass
class PoolFixture:
    opportunity_id: int
    eligible_ids: set[int]
    best_id: int
    profile_ids: list[int] = field(default_factory=list)  # index i -> profile id
    user_emails: dict[int, str] = field(default_factory=dict)  # profile id -> email
    by_reason: dict[str, set[int]] = field(default_factory=dict)  # why a profile is ineligible


def make_listing(session: Session, *, slug: str = "genai-bootcamp-pune-bengaluru", **overrides) -> Opportunity:
    now = datetime.now(timezone.utc)
    values = dict(
        slug=slug,
        title="GenAI bootcamp",
        type="workshop",
        summary="Hands-on GenAI + Python + Kubernetes bootcamp.",
        description_md="Three days of hands-on delivery.",
        location_mode="onsite",
        city="Pune",
        locations_json=json.dumps([{"city": "Pune", "country": "India"}, {"city": "Bengaluru", "country": "India"}]),
        starts_on=STARTS_ON,
        ends_on=ENDS_ON,
        compensation_min=8000,
        compensation_max=10000,
        compensation_currency="INR",
        compensation_unit="day",
        budget_max=10000,
        budget_currency="INR",
        budget_unit="day",
        min_level="advanced",
        deadline=now + timedelta(days=30),
        partner_display_name="A Pune edtech",
        partner_internal_name="Zenvia Learning Pvt Ltd",
        status="open",
        published_at=now,
    )
    values.update(overrides)
    opp = Opportunity(**values)
    session.add(opp)
    session.flush()
    return opp


def set_listing_topics(session: Session, opp: Opportunity, slugs: tuple[str, ...]) -> None:
    ids = {slug: tid for slug, tid in session.execute(select(Topic.slug, Topic.id))}
    for slug in slugs:
        session.add(OpportunityTopic(opportunity_id=opp.id, topic_id=ids[slug]))
    session.flush()


def make_profile(
    session: Session,
    name: str,
    *,
    topics: dict[str, str],
    city: str | None = "Pune",
    remote_ok: bool = False,
    verified: bool = False,
    rate: tuple[int, str, str] | None = (8000, "INR", "day"),  # (rate_min, currency, unit)
    pro_bono: bool = False,
    available_from: date | None = date(2026, 12, 1),
    blackouts: list[tuple[str, str]] | None = None,
    availability: dict | None = None,
    headline: str | None = None,
    updated_at: datetime | None = None,
) -> TrainerProfile:
    now = datetime.now(timezone.utc)
    slug = name.lower().replace(" ", "-")
    user = AppUser(
        email=f"{slug}@example.test",
        email_verified=True,
        display_name=name,
        oidc_issuer="https://accounts.google.com",
        oidc_subject=f"sub-{slug}",
        created_at=now,
    )
    session.add(user)
    session.flush()
    profile = TrainerProfile(
        user_id=user.id,
        headline=headline or f"{name}, trainer",
        bio_md="",
        city=city,
        remote_ok=remote_ok,
        rate_min=rate[0] if rate else None,
        rate_max=(rate[0] + 2000) if rate else None,
        rate_currency=rate[1] if rate else None,
        rate_unit=rate[2] if rate else None,
        pro_bono=pro_bono,
        verified=verified,
        consent_at=now,
        consent_version="2026-11",
        past_work_json=json.dumps([{"title": f"{name} past delivery", "kind": "workshop", "org": None, "year": 2025}]),
        availability_json=json.dumps(availability if availability is not None else {"mon": ["morning"], "tue": ["morning"]}),
        available_from=available_from,
        blackout_json=json.dumps([{"start": s, "end": e} for s, e in (blackouts or [])]),
        created_at=now,
        updated_at=updated_at or now,
    )
    session.add(profile)
    session.flush()
    ids = {slug_: tid for slug_, tid in session.execute(select(Topic.slug, Topic.id))}
    for topic_slug, level in topics.items():
        session.add(TrainerTopic(profile_id=profile.id, topic_id=ids[topic_slug], level=level))
    session.flush()
    return profile


def seed_pool(session: Session) -> PoolFixture:
    opp = make_listing(session)
    set_listing_topics(session, opp, LISTING_TOPICS)
    profiles: list[TrainerProfile] = []
    reasons: dict[str, set[int]] = {k: set() for k in ("level", "city", "blackout", "available_from", "rate", "topic")}
    eligible: set[int] = set()

    def add(i: int, **kw) -> TrainerProfile:
        p = make_profile(session, f"Trainer {i:02d}", **kw)
        profiles.append(p)
        return p

    # 0: the obvious best.
    best = add(0, topics={t: "expert" for t in LISTING_TOPICS}, verified=True)
    eligible.add(best.id)
    # 1-16: eligible, varied (advanced/expert on 1-2 topics, both cities, case variants, pro bono).
    for i in range(1, 17):
        topics = {LISTING_TOPICS[i % 3]: "advanced" if i % 2 else "expert"}
        if i % 4 == 0:
            topics[LISTING_TOPICS[(i + 1) % 3]] = "intermediate"
        p = add(
            i,
            topics=topics,
            city="Bengaluru" if i % 2 else "pune",
            verified=i % 5 == 0,
            rate=None if i % 6 == 0 else (6000 + 200 * i, "INR", "day"),
            pro_bono=i % 6 == 0,
        )
        eligible.add(p.id)
    # 17-24: only intermediate (level too low).
    for i in range(17, 25):
        p = add(i, topics={t: "intermediate" for t in LISTING_TOPICS})
        reasons["level"].add(p.id)
    # 25-31: wrong city (an onsite listing ignores remote_ok).
    for i in range(25, 32):
        p = add(i, topics={"python": "expert"}, city="Mumbai", remote_ok=True)
        reasons["city"].add(p.id)
    # 32-38: blacked out over the dates.
    for i in range(32, 39):
        p = add(i, topics={"python": "expert"}, blackouts=[("2027-02-25", "2027-03-02")])
        reasons["blackout"].add(p.id)
    # 39-44: not available until after the start.
    for i in range(39, 45):
        p = add(i, topics={"python": "expert"}, available_from=date(2027, 3, 15))
        reasons["available_from"].add(p.id)
    # 45-51: rate does not fit (too high, wrong unit, wrong currency, no rate).
    rate_variants = [
        (15000, "INR", "day"),
        (500, "INR", "hour"),
        (200, "USD", "day"),
        (15000, "INR", "day"),
        (500, "INR", "hour"),
        (200, "USD", "day"),
        None,
    ]
    for offset, i in enumerate(range(45, 52)):
        p = add(i, topics={"python": "expert"}, rate=rate_variants[offset])
        reasons["rate"].add(p.id)
    # 52-59: none of the listing's topics.
    for i in range(52, POOL_SIZE):
        p = add(i, topics={"ux-design": "expert"})
        reasons["topic"].add(p.id)

    assert len(profiles) == POOL_SIZE and len(eligible) == ELIGIBLE_COUNT
    return PoolFixture(
        opportunity_id=opp.id,
        eligible_ids=eligible,
        best_id=best.id,
        profile_ids=[p.id for p in profiles],
        user_emails={p.id: f"trainer-{i:02d}@example.test" for i, p in enumerate(profiles)},
        by_reason=reasons,
    )
