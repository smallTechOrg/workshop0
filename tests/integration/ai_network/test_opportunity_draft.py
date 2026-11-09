"""Opportunity drafter (spec/agent.md §Opportunity drafter, §Testing; roadmap Phase 11b slice F4).

* REAL `claude-sonnet-5-5` drafts of the five committed forwarded posts under
  `tests/fixtures/opportunity_posts/`, asserted against each `<name>.expected.json`, incl. the
  prompt-injection post. Partners `Zenvia Learning Pvt Ltd` ("A Pune edtech") and `Globex` are
  seeded. Real-key tests skip only when ANTHROPIC_API_KEY / ANTHROPIC_WORKSPACE_ID are genuinely
  absent (the phase gate asserts presence first and greps for SKIPPED).
* Failure paths on the real PostgreSQL DB: keyless / key-without-workspace -> 503 and no usage
  row; guardrail rejection -> 502 with the spent call's row; `LLMError` -> 502, no row.

Key values are never printed.
"""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from structlog.testing import capture_logs

from src.workshop0.ai import anthropic_client, opportunity_draft, pricing
from src.workshop0.ai.anthropic_client import LLMError, LLMResult
from src.workshop0.ai.opportunity_draft import drafted_fields_of, run_opportunity_draft
from src.workshop0.config.settings import get_settings
from src.workshop0.db.models import AiUsage, Opportunity, Partner, Topic
from src.workshop0.db.session import create_db_session
from src.workshop0.observability.logging import configure_logging

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "opportunity_posts"
PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
DRAFT_KEYS = {
    "title", "type", "summary", "description_md", "topic_slugs", "location_mode", "locations", "starts_on", "ends_on",
    "duration_text", "deadline_on", "compensation_min", "compensation_max", "compensation_currency",
    "compensation_unit", "compensation_text", "partner_id", "suggested_partner", "partner_display_name",
    "internal_notes",
}
PUBLIC_FIELDS = ("title", "summary", "description_md", "duration_text", "compensation_text")


def _post(name: str) -> str:
    return (FIXTURES / f"{name}.txt").read_text(encoding="utf-8")


def _expected(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.expected.json").read_text(encoding="utf-8"))


@pytest.fixture
def partner_ids() -> dict[str, int]:
    """Seeds the two partners the spec names; returns {"zenvia": id, "globex": id}."""
    with create_db_session() as session:
        zenvia = Partner(internal_name="Zenvia Learning Pvt Ltd", name_key="zenvia learning pvt ltd", display_name="A Pune edtech")
        globex = Partner(internal_name="Globex", name_key="globex", display_name=None, notes="NEVER SENT TO THE MODEL ZZ-NOTE")
        session.add_all([zenvia, globex])
        session.flush()
        return {"zenvia": zenvia.id, "globex": globex.id}


@pytest.fixture
def real_ai():
    settings = get_settings()
    if not (settings.anthropic_api_key.strip() and settings.anthropic_workspace_id.strip()):
        pytest.skip("ANTHROPIC_API_KEY and ANTHROPIC_WORKSPACE_ID are required for real-API tests")
    anthropic_client.reset_client()
    yield
    anthropic_client.reset_client()


def _usage_rows() -> list[AiUsage]:
    with create_db_session() as session:
        return list(session.scalars(select(AiUsage).order_by(AiUsage.id)))


def _opportunity_count() -> int:
    with create_db_session() as session:
        return session.scalar(select(func.count()).select_from(Opportunity))


def _draft(text: str, *, opportunity_id: int | None = None, keep: bool = False):
    configure_logging("INFO")
    with capture_logs() as events, create_db_session() as session:
        data = run_opportunity_draft(session, text=text, opportunity_id=opportunity_id, keep_partner_identity=keep)
    return data, events


def _assert_one_usage_row(data: dict[str, Any], events: list[dict], *, opportunity_id: int | None = None) -> AiUsage:
    model = get_settings().workshop0_ai_network_model
    rows = _usage_rows()
    assert len(rows) == 1, "each drafting call writes exactly one ai_usage row"
    row = rows[0]
    assert row.model == model == "claude-sonnet-5-5" == data["model"]
    assert (row.purpose, row.workshop_id, row.cv_document_id, row.opportunity_id) == ("opportunity_draft", None, None, opportunity_id)
    assert row.prompt_tokens > 0 and row.completion_tokens > 0
    assert Decimal(row.cost_usd) == pricing.cost_usd(model, row.prompt_tokens, row.completion_tokens) > 0
    assert data["cost_usd"] == float(row.cost_usd) > 0
    logged = [e for e in events if e["event"] == "ai.opportunity_draft"]
    assert len(logged) == 1 and logged[0]["model"] == model and logged[0]["log_level"] == "info"
    return row


def _assert_response_shape(data: dict[str, Any]) -> dict[str, Any]:
    draft = data["draft"]
    assert set(draft) == DRAFT_KEYS, "every draft key is always present"
    assert data["drafted_fields"] == drafted_fields_of(draft)
    curated = _curated_active_slugs()
    assert set(draft["topic_slugs"]) <= curated and len(draft["topic_slugs"]) <= 8
    assert draft["type"] in (None, "workshop", "engagement", "role", "cofacilitation")
    assert draft["location_mode"] in (None, "remote", "onsite", "hybrid")
    assert draft["compensation_currency"] in (None, "INR", "USD")
    assert draft["compensation_unit"] in (None, "hour", "day", "course", "month")
    for field in ("title", "summary", "description_md"):
        value = draft[field] or ""
        assert "@" not in value and not PHONE.search(value), f"contact detail left in public field {field}"
    return draft


def _curated_active_slugs() -> set[str]:
    with create_db_session() as session:
        return set(session.scalars(select(Topic.slug).where(Topic.active.is_(True))))


def _public_text(draft: dict[str, Any]) -> str:
    """Every public field, the locations included (agent.md: locations are public fields)."""
    parts = [str(draft[f]) for f in PUBLIC_FIELDS if draft.get(f)]
    for loc in draft["locations"]:
        parts.extend(v for v in (loc["city"], loc["country"]) if v)
    return "\n".join(parts)


def _cities(draft: dict[str, Any]) -> set[str]:
    return {loc["city"].casefold() for loc in draft["locations"]}


def _assert_locations(draft: dict[str, Any], expected: dict[str, Any]) -> None:
    cities = _cities(draft)
    assert cities == set(expected["location_cities"]), f"drafted cities {sorted(cities)}"
    assert len(draft["locations"]) == len(expected["location_cities"])
    for city in expected.get("location_cities_exclude", []):
        assert city not in cities, f"{city} is not a venue and must not be listed"


# =========================================================================== REAL claude-sonnet-5-5


def test_real_forwarded_genai_workshop(real_ai, partner_ids):
    expected = _expected("forwarded_genai_workshop")
    before = _opportunity_count()
    data, events = _draft(_post("forwarded_genai_workshop"))
    draft = _assert_response_shape(data)
    _assert_one_usage_row(data, events)

    assert draft["type"] == expected["type"]
    assert draft["location_mode"] == expected["location_mode"]
    _assert_locations(draft, expected)
    assert set(expected["topics_include"]) <= set(draft["topic_slugs"])
    comp = expected["compensation"]
    assert (draft["compensation_min"], draft["compensation_max"], draft["compensation_currency"], draft["compensation_unit"]) == (
        comp["min"], comp["max"], comp["currency"], comp["unit"])
    assert (draft["starts_on"], draft["ends_on"], draft["deadline_on"]) == (
        expected["starts_on"], expected["ends_on"], expected["deadline_on"])
    assert draft["partner_id"] == partner_ids["zenvia"] and draft["suggested_partner"] is None
    assert draft["partner_display_name"] == expected["partner_display_name"]
    for word in expected["forbidden_in_public"]:
        assert word.lower() not in _public_text(draft).lower()
    assert expected["internal_notes_contains"] in (draft["internal_notes"] or "")
    assert {"title", "topics", "location", "dates", "deadline", "compensation", "partner", "internal_notes"} <= set(data["drafted_fields"])
    assert _opportunity_count() == before, "the drafter never creates a listing"


def test_real_mentoring_engagement_suggests_a_new_partner(real_ai, partner_ids):
    expected = _expected("mentoring_engagement")
    data, events = _draft(_post("mentoring_engagement"))
    draft = _assert_response_shape(data)
    _assert_one_usage_row(data, events)

    assert draft["type"] == expected["type"] and draft["location_mode"] == "remote" and draft["locations"] == []
    assert set(expected["topics_include"]) <= set(draft["topic_slugs"])
    comp = expected["compensation"]
    assert draft["compensation_min"] == comp["min"] and draft["compensation_currency"] == "USD" and draft["compensation_unit"] == "hour"
    assert draft["compensation_max"] in (comp["max"], None)
    assert draft["partner_id"] is None
    assert expected["suggested_partner_name_contains"] in draft["suggested_partner"]["internal_name"]
    assert "Northwind" not in _public_text(draft), "partner identity is scrubbed from public fields"
    assert "hiring@northwind-cloud.example" in (draft["internal_notes"] or "")
    assert {"partner"} <= set(data["drafted_fields"])


def test_real_course_fee_onsite_course_unit(real_ai, partner_ids):
    expected = _expected("course_fee")
    data, events = _draft(_post("course_fee"))
    draft = _assert_response_shape(data)
    _assert_one_usage_row(data, events)

    assert set(expected["topics_include"]) <= set(draft["topic_slugs"])
    assert draft["location_mode"] == expected["location_mode"]
    _assert_locations(draft, expected)
    comp = expected["compensation"]
    assert draft["compensation_unit"] == comp["unit"] and draft["compensation_currency"] == comp["currency"]
    assert draft["compensation_min"] == comp["min"]
    assert draft["compensation_max"] in (comp["max"], None)
    assert draft["partner_id"] is None and draft["suggested_partner"] is None  # no organisation named


def test_real_multi_city_bootcamp_lists_only_venue_cities(real_ai, partner_ids):
    expected = _expected("multi_city_bootcamp")
    before = _opportunity_count()
    data, events = _draft(_post("multi_city_bootcamp"))
    draft = _assert_response_shape(data)
    _assert_one_usage_row(data, events)

    assert draft["location_mode"] == expected["location_mode"]
    _assert_locations(draft, expected)
    assert all(loc["country"] in expected["location_countries"] for loc in draft["locations"])
    assert set(expected["topics_include"]) <= set(draft["topic_slugs"])
    comp = expected["compensation"]
    assert (draft["compensation_min"], draft["compensation_currency"], draft["compensation_unit"]) == (
        comp["min"], comp["currency"], comp["unit"])
    assert draft["partner_id"] is expected["partner_id"]
    assert expected["suggested_partner_name_contains"] in draft["suggested_partner"]["internal_name"]
    for field in ("title", "summary", "description_md"):
        for word in expected["forbidden_in_public"]:
            assert word.lower() not in (draft[field] or "").lower(), f"{word} left in {field}"
    assert set(expected["drafted_fields_include"]) <= set(data["drafted_fields"])
    assert _opportunity_count() == before


def test_real_prompt_injection_post_is_ignored(real_ai, partner_ids):
    expected = _expected("injection")
    before = _opportunity_count()
    data, events = _draft(_post("injection"))
    draft = _assert_response_shape(data)
    _assert_one_usage_row(data, events)

    assert not set(expected["forbidden_slugs"]) & set(draft["topic_slugs"])
    assert draft["type"] not in expected["forbidden_type_values"]
    assert draft["compensation_unit"] not in expected["forbidden_unit_values"]
    for word in expected["forbidden_in_public"]:
        assert word.lower() not in _public_text(draft).lower()
    assert draft["compensation_max"] != 999999 and draft["compensation_min"] != 999999
    locations = draft["locations"]
    assert isinstance(locations, list) and len(locations) <= expected["locations_max"]
    for loc in locations:
        assert set(loc) == set(expected["location_item_keys"].split(","))
        assert isinstance(loc["city"], str) and 1 <= len(loc["city"]) <= 80
        assert loc["country"] is None or (isinstance(loc["country"], str) and len(loc["country"]) <= 80)
        for word in expected["forbidden_in_locations"]:
            assert word.lower() not in f"{loc['city']} {loc['country'] or ''}".lower()
    assert "python" in draft["topic_slugs"]  # the genuine post content still drafts
    assert draft["partner_id"] == partner_ids["zenvia"]
    assert _opportunity_count() == before, "nothing is created or published"
    with create_db_session() as session:
        assert session.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.status == "open")) == 0


def test_real_usage_row_links_the_given_opportunity(real_ai, partner_ids, client, admin_headers, create_opportunity):
    opp = create_opportunity()
    data, events = _draft(_post("course_fee"), opportunity_id=opp["id"])
    _assert_response_shape(data)
    _assert_one_usage_row(data, events, opportunity_id=opp["id"])


# =========================================================================== failure paths


def _llm(content: dict[str, Any]) -> LLMResult:
    model = get_settings().workshop0_ai_network_model
    return LLMResult(content=content, prompt_tokens=900, completion_tokens=120, cost_usd=pricing.cost_usd(model, 900, 120), latency_ms=500, model=model)


@pytest.mark.parametrize("which", ["key", "workspace"])
def test_unavailable_network_ai_is_503_without_usage(network_ai_disabled, partner_ids, which):
    network_ai_disabled(which=which)
    with pytest.raises(HTTPException) as exc:
        _draft(_post("course_fee"))
    assert exc.value.status_code == 503 and exc.value.detail["code"] == "ai_not_configured"
    assert _usage_rows() == []


def test_llm_error_is_502_logs_cause_and_writes_no_row(monkeypatch, partner_ids):
    def boom(**_kw):
        raise LLMError("http_529", status=529, request_id="req_x")

    monkeypatch.setattr(opportunity_draft.anthropic_client, "call_json", boom)
    configure_logging("INFO")
    with capture_logs() as events, pytest.raises(HTTPException) as exc, create_db_session() as session:
        run_opportunity_draft(session, text=_post("course_fee"), opportunity_id=None, keep_partner_identity=False)
    assert exc.value.status_code == 502 and exc.value.detail["code"] == "ai_draft_failed"
    failed = [e for e in events if e["event"] == "ai.call_failed"]
    assert len(failed) == 1 and failed[0]["purpose"] == "opportunity_draft" and failed[0]["cause"] == "http_529"
    assert failed[0]["request_id"] == "req_x"
    assert "Rs 40,000" not in json.dumps(failed, default=str), "pasted text is never logged"
    assert _usage_rows() == []


def test_guardrail_rejection_is_502_but_records_the_spend(monkeypatch, partner_ids):
    empty = {"title": "", "summary": "", "topics": ["hacking"], "partner": {}, "compensation": {}}
    monkeypatch.setattr(opportunity_draft.anthropic_client, "call_json", lambda **_kw: _llm(empty))
    with pytest.raises(HTTPException) as exc, create_db_session() as session:
        run_opportunity_draft(session, text=_post("course_fee"), opportunity_id=None, keep_partner_identity=False)
    assert exc.value.status_code == 502 and exc.value.detail["code"] == "ai_draft_failed"
    rows = _usage_rows()
    assert len(rows) == 1 and rows[0].purpose == "opportunity_draft" and rows[0].cost_usd > 0


def test_stubbed_call_sees_only_active_topics_and_partner_names_not_notes(monkeypatch, partner_ids):
    with create_db_session() as session:
        session.execute(Topic.__table__.update().where(Topic.slug == "react").values(active=False))
        session.add(Partner(internal_name="Dormant Co", name_key="dormant co", active=False))
    seen: list[dict[str, Any]] = []

    def fake(**kw):
        seen.append(kw)
        return _llm({"title": "React course", "summary": "A course.", "topics": ["react", "python"], "partner": {}, "compensation": {}})

    monkeypatch.setattr(opportunity_draft.anthropic_client, "call_json", fake)
    data, _events = _draft(_post("course_fee"))
    user = seen[0]["user"]
    assert "- python — " in user and "- react — " not in user
    assert "Zenvia Learning Pvt Ltd" in user and "Globex" in user and "Dormant Co" not in user
    assert "ZZ-NOTE" not in user
    assert data["draft"]["topic_slugs"] == ["python"], "an inactive slug is dropped even if the model returns it"
