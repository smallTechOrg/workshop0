"""POST/GET /api/admin/opportunity-draft* (spec/api.md §Phase 11b, agent.md §Testing — Endpoint).

Real `claude-sonnet-5-5` via the admin API for the happy paths; validation, auth, rate limit and
keyless behaviour on the real PostgreSQL DB. Real-key tests skip only when the key/workspace id
are genuinely absent (the phase gate asserts presence first).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import httpx2
import pytest
from sqlalchemy import func, select

from src.workshop0.ai import anthropic_client
from src.workshop0.config.settings import get_settings
from src.workshop0.db.models import AiUsage, Opportunity, Partner
from src.workshop0.db.session import create_db_session
from src.workshop0.services import ratelimit

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "opportunity_posts"
URL = "/api/admin/opportunity-draft"
POST = (FIXTURES / "forwarded_genai_workshop.txt").read_text(encoding="utf-8")
DRAFT_KEYS = {
    "title", "type", "summary", "description_md", "topic_slugs", "location_mode", "locations", "starts_on", "ends_on",
    "duration_text", "deadline_on", "compensation_min", "compensation_max", "compensation_currency",
    "compensation_unit", "compensation_text", "partner_id", "suggested_partner", "partner_display_name",
    "internal_notes",
}


@pytest.fixture
def real_ai():
    settings = get_settings()
    if not (settings.anthropic_api_key.strip() and settings.anthropic_workspace_id.strip()):
        pytest.skip("ANTHROPIC_API_KEY and ANTHROPIC_WORKSPACE_ID are required for real-API tests")
    anthropic_client.reset_client()
    yield
    anthropic_client.reset_client()


def _usage() -> list[AiUsage]:
    with create_db_session() as session:
        return list(session.scalars(select(AiUsage).order_by(AiUsage.id)))


def _opportunities() -> int:
    with create_db_session() as session:
        return session.scalar(select(func.count()).select_from(Opportunity))


@pytest.fixture
def zenvia() -> int:
    with create_db_session() as session:
        p = Partner(internal_name="Zenvia Learning Pvt Ltd", name_key="zenvia learning pvt ltd", display_name="A Pune edtech")
        session.add(p)
        session.flush()
        return p.id


# --------------------------------------------------------------------------- auth + validation (no AI spend)


def test_both_endpoints_require_admin_auth(client):
    assert client.get(f"{URL}/config").status_code == 401
    assert client.post(URL, json={"text": POST}).status_code == 401
    assert client.get(f"{URL}/config", headers={"X-Admin-Key": "wrong"}).status_code == 401
    assert _usage() == []


@pytest.mark.parametrize("length", [39, 20001])
def test_text_length_bounds_are_validation_errors_without_usage(client, admin_headers, length):
    response = client.post(URL, json={"text": "x" * length}, headers=admin_headers)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "validation_error"
    assert detail["message"] == "text: paste between 40 and 20000 characters"
    assert _usage() == []


def test_text_is_trimmed_before_the_length_check(client, admin_headers):
    padded = "   " + "x" * 30 + " " * 100
    response = client.post(URL, json={"text": padded}, headers=admin_headers)
    assert response.status_code == 422 and _usage() == []


def test_missing_text_and_unknown_opportunity_are_validation_errors(client, admin_headers):
    assert client.post(URL, json={}, headers=admin_headers).status_code == 422
    response = client.post(URL, json={"text": POST, "opportunity_id": 999999}, headers=admin_headers)
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "validation_error", "message": "opportunity_id: no opportunity with this id"}
    assert _usage() == []


def test_rate_limit_429_with_retry_after_and_no_anthropic_request(client, admin_headers, monkeypatch):
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(500)

    settings = get_settings().model_copy(update={"anthropic_api_key": "k-test", "anthropic_workspace_id": "w-test"})
    mock = anthropic_client.build_client(settings, http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    monkeypatch.setattr(anthropic_client, "get_client", lambda: mock)
    with create_db_session() as session:
        for _ in range(60):
            ratelimit.hit(session, "opportunity_draft", 60, 3600)
    response = client.post(URL, json={"text": POST}, headers=admin_headers)
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "rate_limited"
    assert int(response.headers["Retry-After"]) > 0
    assert requests == [] and _usage() == []


# --------------------------------------------------------------------------- keyless


@pytest.mark.parametrize("which", ["key", "workspace"])
def test_keyless_config_unavailable_post_503_no_request_and_listing_flow_intact(
    client, admin_headers, network_ai_disabled, monkeypatch, create_opportunity, which
):
    network_ai_disabled(which=which)
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(500)

    settings = get_settings().model_copy(update={"anthropic_api_key": "k-test", "anthropic_workspace_id": "w-test"})
    mock = anthropic_client.build_client(settings, http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    monkeypatch.setattr(anthropic_client, "get_client", lambda: mock)

    config = client.get(f"{URL}/config", headers=admin_headers)
    assert config.status_code == 200
    assert config.json()["data"] == {"available": False, "model": "claude-sonnet-5-5"}

    response = client.post(URL, json={"text": POST}, headers=admin_headers)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ai_not_configured"
    assert requests == [] and _usage() == []

    # creating and publishing a listing still works
    opp = create_opportunity()
    published = client.patch(f"/api/admin/opportunities/{opp['id']}", json={"status": "open"}, headers=admin_headers)
    assert published.status_code == 200, published.text
    assert published.json()["data"]["opportunity"]["status"] == "open"


# --------------------------------------------------------------------------- real API


def test_config_available_with_real_keys(real_ai, client, admin_headers):
    response = client.get(f"{URL}/config", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == {"data": {"available": True, "model": "claude-sonnet-5-5"}, "error": None}


def test_real_post_without_opportunity_id(real_ai, client, admin_headers, zenvia):
    before = _opportunities()
    response = client.post(URL, json={"text": POST, "keep_partner_identity": False}, headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["error"] is None
    data = body["data"]
    assert set(data) == {"draft", "drafted_fields", "cost_usd", "model"}
    assert set(data["draft"]) == DRAFT_KEYS
    assert data["model"] == "claude-sonnet-5-5"
    assert data["draft"]["partner_id"] == zenvia and data["draft"]["partner_display_name"] == "A Pune edtech"
    assert data["draft"]["compensation_unit"] == "day" and data["draft"]["location_mode"] == "hybrid"
    assert "Zenvia" not in (data["draft"]["title"] or "") + (data["draft"]["summary"] or "") + (data["draft"]["description_md"] or "")
    assert "title" in data["drafted_fields"] and "internal_notes" in data["drafted_fields"]

    rows = _usage()
    assert len(rows) == 1
    assert (rows[0].purpose, rows[0].opportunity_id, rows[0].workshop_id) == ("opportunity_draft", None, None)
    assert data["cost_usd"] == float(rows[0].cost_usd) > 0
    assert Decimal(str(data["cost_usd"])) == Decimal(rows[0].cost_usd).quantize(Decimal("0.000001"))
    assert _opportunities() == before, "the endpoint never creates a listing"


def test_real_post_with_opportunity_id_links_usage_and_leaves_the_listing_untouched(
    real_ai, client, admin_headers, create_opportunity, zenvia
):
    opp = create_opportunity()
    before = client.get(f"/api/admin/opportunities/{opp['id']}", headers=admin_headers).json()
    response = client.post(
        URL,
        json={"text": POST, "opportunity_id": opp["id"], "keep_partner_identity": True},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert set(response.json()["data"]["draft"]) == DRAFT_KEYS
    rows = _usage()
    assert len(rows) == 1 and rows[0].opportunity_id == opp["id"]
    after = client.get(f"/api/admin/opportunities/{opp['id']}", headers=admin_headers).json()
    assert json.dumps(after, sort_keys=True) == json.dumps(before, sort_keys=True)
