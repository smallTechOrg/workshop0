"""Pure board rules: slug derivation, effective status (and its SQL twin), request-model
validation messages."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from src.workshop0.db.models import Opportunity
from src.workshop0.services.opportunities import (
    OpportunityCreate,
    OpportunityPatch,
    effective_status,
    effective_status_predicate,
)
from src.workshop0.services.topics import slugify

NOW = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("C# / .NET 2", "c-net-2"),
        ("Elixir", "elixir"),
        ("  Generative AI & LLMs  ", "generative-ai-llms"),
        ("CI/CD", "ci-cd"),
        ("--Rust--", "rust"),
        ("Ünïcode Stuff", "n-code-stuff"),
        ("!!!", ""),
        ("a" * 60, "a" * 48),
        ("a" * 47 + " b", "a" * 47),  # cut at 48 lands on '-': stripped
    ],
)
def test_slugify(name, slug):
    assert slugify(name) == slug


def _opp(status: str, deadline: datetime) -> Opportunity:
    return Opportunity(status=status, deadline=deadline)


@pytest.mark.parametrize(
    ("status", "delta", "expected"),
    [
        ("draft", timedelta(days=-1), "draft"),
        ("draft", timedelta(days=1), "draft"),
        ("closed", timedelta(days=1), "closed"),
        ("closed", timedelta(days=-1), "closed"),
        ("open", timedelta(seconds=1), "open"),
        ("open", timedelta(seconds=0), "expired"),  # deadline <= now is expired
        ("open", timedelta(seconds=-1), "expired"),
    ],
)
def test_effective_status(status, delta, expected):
    assert effective_status(_opp(status, NOW + delta), NOW) == expected


def test_effective_status_treats_naive_db_values_as_utc():
    naive = (NOW + timedelta(minutes=1)).replace(tzinfo=None)
    assert effective_status(_opp("open", naive), NOW) == "open"


def test_sql_predicates_mirror_effective_status():
    def sql(status):
        return str(effective_status_predicate(status, NOW).compile(dialect=postgresql.dialect()))

    assert "opportunity.status = %(status_1)s AND opportunity.deadline > %(deadline_1)s" == sql("open")
    assert "opportunity.deadline <= %(deadline_1)s" in sql("expired")
    assert sql("draft") == "opportunity.status = %(status_1)s"


def _body(**overrides) -> dict:
    body = {"title": "A title", "type": "workshop", "summary": "s", "topic_ids": [1],
            "deadline": "2026-11-30T18:29:59Z"}
    body.update(overrides)
    return body


def _message(model, body) -> str:
    with pytest.raises(ValidationError) as info:
        model(**body)
    error = info.value.errors()[0]
    return f"{error['loc'][0]}: {error['msg'].removeprefix('Value error, ')}"


def test_create_defaults_and_trimming():
    body = OpportunityCreate(**_body(title="  Hello  ", city="   ", partner_display_name=""))
    assert body.title == "Hello" and body.city is None and body.partner_display_name is None
    assert body.status == "draft" and body.location_mode == "remote" and body.description_md == ""
    assert body.deadline == datetime(2026, 11, 30, 18, 29, 59, tzinfo=timezone.utc)


def test_offset_deadline_is_normalised_to_utc():
    body = OpportunityCreate(**_body(deadline="2026-12-01T00:00:00+05:30"))
    assert body.deadline == datetime(2026, 11, 30, 18, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"deadline": "2026-11-30T18:29:59"}, "deadline: include a time zone, e.g. 2026-11-30T18:29:59Z"),
        ({"topic_ids": []}, "topic_ids: choose 1 to 8 topics"),
        ({"topic_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9]}, "topic_ids: choose 1 to 8 topics"),
        ({"topic_ids": [3, 3]}, "topic_ids: choose each topic only once"),
        ({"type": "Workshop"}, "type: must be one of workshop, engagement, role, cofacilitation"),
        ({"status": "expired"}, "status: must be one of draft, open, closed"),
    ],
)
def test_create_validation_messages(overrides, message):
    assert _message(OpportunityCreate, _body(**overrides)) == message


def test_patch_tracks_only_the_fields_sent():
    patch = OpportunityPatch(summary="x", city=None)
    assert patch.model_fields_set == {"summary", "city"}
    assert OpportunityPatch().model_fields_set == set()


# --------------------------------------------------------------------------- Phase 11c locations


def test_locations_are_normalized_and_deduped():
    body = OpportunityCreate(**_body(locations=[
        {"city": " pune "}, {"city": "PUNE", "country": "  "}, {"city": "Pune", "country": " India "},
        {"city": "  New   Delhi "},
    ]))
    assert body.locations == [
        {"city": "pune", "country": None},
        {"city": "Pune", "country": "India"},
        {"city": "New Delhi", "country": None},
    ]
    assert OpportunityPatch(locations=None).locations == []
    assert "locations" not in OpportunityPatch(city="Pune").model_fields_set


@pytest.mark.parametrize(
    ("locations", "message"),
    [
        ("Pune", "locations: each location needs a city and an optional country"),
        (["Pune"], "locations: each location needs a city and an optional country"),
        ([{"country": "India"}], "locations: each location needs a city and an optional country"),
        ([{"city": "Pune", "state": "MH"}], "locations: each location needs a city and an optional country"),
        ([{"city": 5}], "locations: each location needs a city and an optional country"),
        ([{"city": "   "}], "locations: city must be 1–80 characters"),
        ([{"city": "c" * 81}], "locations: city must be 1–80 characters"),
        ([{"city": "Pune", "country": "c" * 81}], "locations: country must be at most 80 characters"),
        ([{"city": "Pune", "country": 7}], "locations: country must be at most 80 characters"),
        ([{"city": f"City {i}"} for i in range(11)], "locations: at most 10 locations"),
    ],
)
def test_locations_validation_messages(locations, message):
    assert _message(OpportunityCreate, _body(locations=locations)) == message


def test_locations_cap_is_checked_after_dedupe():
    items = [{"city": f"City {i}"} for i in range(10)] + [{"city": "city 0"}]
    assert len(OpportunityCreate(**_body(locations=items)).locations) == 10
