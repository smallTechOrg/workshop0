"""Completeness = ten checks × 10 % (api.md §Phase 11) on 5 hand-built profiles.

Profiles are written straight to the DB (not via the API) so every check is set by hand,
then scored both by `services.profiles.completeness` and by GET /api/me/profile."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from src.workshop0.db.models import CvDocument, Topic, TrainerProfile, TrainerTopic
from src.workshop0.db.session import create_db_session
from src.workshop0.services.profiles import Completeness, completeness

ALL_CHECKS = ["headline", "bio", "topics", "location", "link", "past_work", "rate", "availability",
              "available_from", "cv"]


def _build(user_id: int, *, topics: int, cv: bool, **columns) -> int:
    now = datetime.now(timezone.utc)
    with create_db_session() as session:
        profile = TrainerProfile(user_id=user_id, consent_at=now, consent_version="2026-11", **columns)
        session.add(profile)
        session.flush()
        for topic in session.scalars(select(Topic).order_by(Topic.id).limit(topics)):
            session.add(TrainerTopic(profile_id=profile.id, topic_id=topic.id, level="advanced"))
        if cv:
            session.add(CvDocument(user_id=user_id, source="text", sha256="0" * 64, text_extract="cv",
                                   draft_status="skipped"))
        return profile.id


CASES = [
    pytest.param(
        # 1 — everything: 100 %
        dict(headline="GenAI trainer", bio_md="b" * 80, city="Pune", remote_ok=False,
             github_url="https://github.com/x", past_work_json=json.dumps([{"title": "t", "kind": "talk"}]),
             rate_min=1, rate_max=2, rate_currency="INR", rate_unit="day",
             availability_json=json.dumps({"tue": ["evening"]}), available_from=date(2026, 12, 1)),
        3, True, [], id="complete",
    ),
    pytest.param(
        # 2 — the bare minimum the API accepts (remote_ok defaults true → location passes): 20 %
        dict(headline="Trainer", remote_ok=True),
        1, False,
        ["bio", "topics", "link", "past_work", "rate", "availability", "available_from", "cv"],
        id="minimal",
    ),
    pytest.param(
        # 3 — boundaries just short: bio 79 chars, 2 topics, rate missing unit, empty day lists,
        #     no city and not remote: 20 % (headline + cv)
        dict(headline="Data engineer", bio_md="b" * 79, city=None, remote_ok=False,
             rate_min=100, rate_max=200, rate_currency="USD", rate_unit=None,
             availability_json=json.dumps({"mon": [], "tue": []})),
        2, True,
        ["bio", "topics", "location", "link", "past_work", "rate", "availability", "available_from"],
        id="just-short",
    ),
    pytest.param(
        # 4 — pro_bono satisfies rate without a range; website link; city only: 70 %
        dict(headline="Mentor", bio_md="x" * 200, city="Chennai", remote_ok=False, pro_bono=True,
             website_url="https://me.example", availability_json=json.dumps({"sat": ["morning"]})),
        5, False, ["past_work", "available_from", "cv"], id="pro-bono",
    ),
    pytest.param(
        # 5 — rate range without currency fails; linkedin counts as a link: 70 %
        dict(headline="Cloud architect", bio_md="y" * 100, remote_ok=True,
             linkedin_url="https://www.linkedin.com/in/x", rate_min=10, rate_max=20, rate_currency=None,
             rate_unit="hour", past_work_json=json.dumps([{"title": "a", "kind": "course"}]),
             available_from=date(2027, 1, 1)),
        3, False, ["rate", "availability", "cv"], id="rate-no-currency",
    ),
]


@pytest.mark.parametrize("columns, topics, cv, missing", CASES)
def test_completeness_ten_check_formula(make_user, signed_in_client, columns, topics, cv, missing):
    user = make_user("score@example.test")
    profile_id = _build(user.id, topics=topics, cv=cv, **columns)
    expected = Completeness(pct=100 - 10 * len(missing), missing=missing)

    with create_db_session() as session:
        profile = session.get(TrainerProfile, profile_id)
        assert completeness(profile) == expected
        # explicit counts (the admin pool's batch path) agree with the session path
        assert completeness(profile, topic_count=topics, has_cv=cv) == expected

    response = signed_in_client(user).get("/api/me/profile")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["completeness"] == {"pct": expected.pct, "missing": missing}
    # `missing` keys are always in formula order
    assert missing == [c for c in ALL_CHECKS if c in missing]


def test_completeness_needs_counts_for_a_detached_profile():
    with pytest.raises(ValueError):
        completeness(TrainerProfile(headline="x"))
    detached = TrainerProfile(headline="x", remote_ok=True, bio_md="", past_work_json="[]",
                              availability_json="{}", pro_bono=False)
    assert completeness(detached, topic_count=0, has_cv=False).pct == 20
