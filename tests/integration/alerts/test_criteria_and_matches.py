from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from src.workshop0.db.models import Opportunity
from src.workshop0.db.session import create_db_session
from src.workshop0.services import alerts


def _opp(**kw) -> Opportunity:
    base = dict(
        slug="x", title="T", type="workshop", summary="s", location_mode="remote", city=None,
        locations_json="[]", deadline=datetime.now(timezone.utc) + timedelta(days=3), status="open",
    )
    base.update(kw)
    return Opportunity(**base)


def _err(session, criteria) -> str:
    with pytest.raises(HTTPException) as exc:
        alerts.validate_criteria(session, criteria)
    assert exc.value.status_code == 422 and exc.value.detail["code"] == "validation_error"
    return exc.value.detail["message"]


def test_validate_normalises():
    with create_db_session() as s:
        out = alerts.validate_criteria(
            s,
            {
                "types": ["role", "role"],
                "topic_slugs": ["python", "python"],
                "cities": ["  Pune ", "pune", "New   Delhi"],
            },
        )
    assert out == {
        "types": ["role"], "topic_slugs": ["python"], "location_modes": [], "cities": ["Pune", "New Delhi"]
    }


@pytest.mark.parametrize(
    "criteria,field",
    [
        ({}, "at least one"),
        ({"types": []}, "at least one"),
        ({"types": ["role"], "bogus": 1}, "bogus"),
        ({"types": ["nope"]}, "types"),
        ({"types": "role"}, "types"),
        ({"types": [1]}, "types"),
        ({"location_modes": ["moon"]}, "location_modes"),
        ({"topic_slugs": ["no-such-topic"]}, "topic_slugs"),
        ({"cities": ["   "]}, "cities"),
        ({"cities": ["x" * 81]}, "cities"),
        ({"cities": [f"c{i}" for i in range(6)]}, "cities"),
        ({"cities": [None]}, "cities"),
    ],
)
def test_validate_rejects(criteria, field):
    with create_db_session() as s:
        assert field in _err(s, criteria)


def test_validate_rejects_non_object_and_too_many_slugs():
    with create_db_session() as s:
        _err(s, ["role"])
        from sqlalchemy import select
        from src.workshop0.db.models import Topic

        slugs = list(s.scalars(select(Topic.slug).limit(11)))
        assert len(slugs) == 11
        assert "topic_slugs" in _err(s, {"topic_slugs": slugs})
        assert alerts.validate_criteria(s, {"topic_slugs": slugs[:10]})["topic_slugs"] == slugs[:10]


def test_city_case_insensitive_dedupe_boundary():
    with create_db_session() as s:
        out = alerts.validate_criteria(s, {"cities": ["x" * 80, "X" * 80, "a", "b", "c", "d"]})
        assert len(out["cities"]) == 5


def test_matches_rules():
    pune = '[{"city": "Pune", "country": "India"}]'
    o = _opp(type="workshop", location_mode="onsite", city="Pune", locations_json=pune)
    t = frozenset({"python", "aws"})
    assert alerts.matches({}, o, t)  # empty lists never exclude
    assert alerts.matches({"types": ["workshop"]}, o, t)
    assert not alerts.matches({"types": ["role"]}, o, t)
    assert alerts.matches({"topic_slugs": ["aws", "react"]}, o, t)
    assert not alerts.matches({"topic_slugs": ["react"]}, o, t)
    assert not alerts.matches({"topic_slugs": ["react"]}, o, frozenset())
    assert alerts.matches({"location_modes": ["onsite", "hybrid"]}, o, t)
    assert not alerts.matches({"location_modes": ["remote"]}, o, t)
    assert alerts.matches({"cities": ["  PUNE "]}, o, t)
    assert not alerts.matches({"cities": ["Delhi"]}, o, t)
    # AND across lists
    assert alerts.matches({"types": ["workshop"], "cities": ["pune"], "topic_slugs": ["python"]}, o, t)
    assert not alerts.matches({"types": ["workshop"], "cities": ["pune"], "topic_slugs": ["react"]}, o, t)


def test_remote_listing_never_satisfies_cities():
    o = _opp(location_mode="remote", city="Pune")  # stale city on a remote listing
    assert not alerts.matches({"cities": ["Pune"]}, o, frozenset())
    assert alerts.matches({"location_modes": ["remote"]}, o, frozenset())


def test_legacy_city_mirror_is_used():
    o = _opp(location_mode="hybrid", city="Goa", locations_json="[]")
    assert alerts.matches({"cities": ["goa"]}, o, frozenset())
