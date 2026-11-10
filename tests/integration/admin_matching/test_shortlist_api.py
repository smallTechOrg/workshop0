"""POST/GET /api/admin/opportunities/{id}/shortlist (spec/api.md §Phase 12)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from src.workshop0.config.settings import get_settings
from src.workshop0.db.models import AiUsage, MatchSuggestion
from src.workshop0.db.session import create_db_session
from src.workshop0.services import ratelimit
from tests.fixtures.network_pool import seed_pool


def _seed():
    with create_db_session() as session:
        return seed_pool(session)


def _usage_count() -> int:
    with create_db_session() as session:
        return session.scalar(select(func.count()).select_from(AiUsage))


def test_requires_admin_and_unknown_listing_is_404(client, admin_headers):
    pool = _seed()
    url = f"/api/admin/opportunities/{pool.opportunity_id}/shortlist"
    assert client.post(url).status_code == 401
    assert client.get(url).status_code == 401
    assert client.post("/api/admin/opportunities/999999/shortlist", headers=admin_headers).status_code == 404
    assert client.get("/api/admin/opportunities/abc/shortlist", headers=admin_headers).status_code in (404, 422)


def test_get_before_any_run_is_empty(client, admin_headers):
    pool = _seed()
    r = client.get(f"/api/admin/opportunities/{pool.opportunity_id}/shortlist", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["data"] == {"run_id": None, "ranked_by": None, "suggestions": [], "cost_usd": 0.0}


def test_keyless_post_ranks_by_rules_and_get_returns_the_same_latest_run(client, admin_headers, network_ai_disabled):
    network_ai_disabled()
    pool = _seed()
    url = f"/api/admin/opportunities/{pool.opportunity_id}/shortlist"
    r = client.post(url, headers=admin_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["ranked_by"] == "rules" and data["cost_usd"] == 0
    assert len(data["suggestions"]) == 10 and len(data["run_id"]) == 22
    trainer_ids = [s["trainer"]["id"] for s in data["suggestions"]]
    assert set(trainer_ids) <= pool.eligible_ids and trainer_ids[0] == pool.best_id
    first = data["suggestions"][0]
    assert first["rank"] == 1 and first["reason"] is None and 0 < first["rule_score"] <= 1
    assert first["invited"] is False
    assert {"id", "display_name", "email", "headline", "topics", "verified", "completeness_pct"} <= set(first["trainer"])
    assert _usage_count() == 0
    again = client.get(url, headers=admin_headers).json()["data"]
    assert again == data
    # a second run replaces "latest"
    second = client.post(url, headers=admin_headers).json()["data"]
    assert second["run_id"] != data["run_id"]
    assert client.get(url, headers=admin_headers).json()["data"]["run_id"] == second["run_id"]


def test_rate_limited_after_20_runs_per_hour_with_no_ranking(client, admin_headers, network_ai_disabled):
    network_ai_disabled()
    pool = _seed()
    with create_db_session() as session:
        for _ in range(20):
            ratelimit.hit(session, "shortlist_rank", 20, 3600)
    r = client.post(f"/api/admin/opportunities/{pool.opportunity_id}/shortlist", headers=admin_headers)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"
    with create_db_session() as session:
        assert session.scalar(select(func.count()).select_from(MatchSuggestion)) == 0


def test_real_post_returns_ai_ranking_cost_equal_to_the_usage_row(client, admin_headers):
    settings = get_settings()
    if not (settings.anthropic_api_key.strip() and settings.anthropic_workspace_id.strip()):
        pytest.skip("ANTHROPIC_API_KEY and ANTHROPIC_WORKSPACE_ID are required for real-API tests")
    pool = _seed()
    url = f"/api/admin/opportunities/{pool.opportunity_id}/shortlist"
    data = client.post(url, headers=admin_headers).json()["data"]
    assert data["ranked_by"] == "ai" and 1 <= len(data["suggestions"]) <= 10
    ids = [s["trainer"]["id"] for s in data["suggestions"]]
    assert set(ids) <= pool.eligible_ids and pool.best_id in ids[:3]
    with create_db_session() as session:
        rows = list(session.scalars(select(AiUsage)))
    assert len(rows) == 1 and rows[0].cost_usd > 0 and data["cost_usd"] == float(rows[0].cost_usd)
    assert client.get(url, headers=admin_headers).json()["data"]["cost_usd"] == data["cost_usd"]
