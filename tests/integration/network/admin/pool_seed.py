"""S8 pool-api seed helpers + constants (imported by conftest.py and the tests)."""


from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import select

POOL_SIZE = 60
NEEDLE = "needle"
CV_TEXT_SENTINEL = "ZZ-CV-TEXT-SENTINEL-4b2e"
POOL_TAG = "bengaluru"
RATE_UNITS = ("hour", "day", "course", "month")


@dataclass
class Pool:
    ids: list[int]  # index i -> profile id
    user_ids: list[int]
    emails: list[str]
    by_q: set[int] = field(default_factory=set)
    by_topic: dict[str, set[int]] = field(default_factory=dict)
    verified: set[int] = field(default_factory=set)
    unverified: set[int] = field(default_factory=set)
    by_tag: dict[str, set[int]] = field(default_factory=dict)
    with_cv: dict[int, int] = field(default_factory=dict)  # profile id -> cv_document id


def _topic_ids(session) -> dict[str, int]:
    from src.workshop0.db.models import Topic

    return {slug: tid for slug, tid in session.execute(select(Topic.slug, Topic.id)).all()}


def seed_profile(
    session,
    *,
    email: str,
    display_name: str,
    headline: str,
    bio_md: str = "",
    created_at: datetime | None = None,
    verified: bool = False,
    topics: dict[str, str] | None = None,
    tags: list[str] | None = None,
    rate: tuple[int, int, str, str] | None = None,
    city: str | None = None,
):
    """Insert app_user + trainer_profile (+ topics/tags). Returns the profile row."""
    from src.workshop0.db.models import AppUser, TrainerProfile, TrainerTag, TrainerTopic

    now = created_at or datetime.now(timezone.utc)
    user = AppUser(
        email=email.lower(),
        email_verified=True,
        display_name=display_name,
        oidc_issuer="https://accounts.google.com",
        oidc_subject=f"sub-{email}",
        created_at=now,
    )
    session.add(user)
    session.flush()
    profile = TrainerProfile(
        user_id=user.id,
        headline=headline,
        bio_md=bio_md,
        city=city,
        remote_ok=True,
        rate_min=rate[0] if rate else None,
        rate_max=rate[1] if rate else None,
        rate_currency=rate[2] if rate else None,
        rate_unit=rate[3] if rate else None,
        verified=verified,
        verified_at=now if verified else None,
        verified_by="seed" if verified else None,
        consent_at=now,
        consent_version="2026-11",
        past_work_json=json.dumps([{"title": "Intro talk", "kind": "talk", "org": None, "year": 2025}]),
        availability_json=json.dumps({"mon": ["morning"]}),
        available_from=date(2026, 12, 1),
        created_at=now,
        updated_at=now,
    )
    session.add(profile)
    session.flush()
    topic_ids = _topic_ids(session) if topics else {}
    for slug, level in (topics or {}).items():
        session.add(TrainerTopic(profile_id=profile.id, topic_id=topic_ids[slug], level=level))
    for tag in tags or []:
        session.add(TrainerTag(profile_id=profile.id, tag=tag))
    session.flush()
    return profile


def seed_cv(
    session,
    user_id: int,
    *,
    storage_key: str | None,
    source: str = "pdf",
    original_filename: str | None = "cv.pdf",
    text_extract: str = CV_TEXT_SENTINEL,
    size_bytes: int = 0,
):
    from src.workshop0.db.models import CvDocument

    cv = CvDocument(
        user_id=user_id,
        source=source,
        original_filename=original_filename,
        storage_key=storage_key,
        content_type="application/pdf" if source == "pdf" else None,
        size_bytes=size_bytes,
        sha256="0" * 64,
        text_extract=text_extract,
        draft_status="ready",
    )
    session.add(cv)
    session.flush()
    return cv


@dataclass
class SpendSeed:
    trainer_profile_id: int
    trainer_cost: float
    total_cost: float
    call_count: int
    prompt_tokens: int
    completion_tokens: int
    by_purpose: dict[str, tuple[float, int]]


# (purpose, cost, prompt, completion, attach_to) — attach_to: "a" (trainer A's CV),
# "b" (trainer B's CV), None (no CV). Help-desk rows below carry a workshop_id.
NETWORK_ROWS = (
    ("profile_draft", "0.012345", 1200, 340, "a"),
    ("profile_draft", "0.000655", 300, 80, "a"),
    ("profile_draft", "0.004000", 800, 200, "b"),
    ("shortlist_rank", "0.021000", 4000, 600, None),
)
HELPDESK_ROWS = (("triage_answer", "5.000000", 99999, 9999), ("triage_answer", "1.250000", 5000, 500))


