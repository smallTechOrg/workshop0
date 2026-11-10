"""Shortlist ranker (spec/agent.md §Testing - Ranker): real claude-sonnet-5-5 on the 60-profile pool."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from src.workshop0.ai import anthropic_client, shortlist_rank
from src.workshop0.ai.anthropic_client import LLMError
from src.workshop0.config.settings import get_settings
from src.workshop0.db.models import AiUsage, MatchSuggestion, Opportunity
from src.workshop0.db.session import create_db_session
from src.workshop0.services import matching
from tests.fixtures.network_pool import make_listing, make_profile, seed_pool, set_listing_topics


@pytest.fixture
def real_ai():
    settings = get_settings()
    if not (settings.anthropic_api_key.strip() and settings.anthropic_workspace_id.strip()):
        pytest.skip("ANTHROPIC_API_KEY and ANTHROPIC_WORKSPACE_ID are required for real-API tests")
    anthropic_client.reset_client()
    yield
    anthropic_client.reset_client()


def _usage(session) -> list[AiUsage]:
    return list(session.scalars(select(AiUsage).order_by(AiUsage.id)))


# --------------------------------------------------------------------------- real API


def test_real_ranking_obeys_eligible_set_top3_best_and_records_cost(real_ai):
    with create_db_session() as session:
        pool = seed_pool(session)
        run = shortlist_rank.run_shortlist(session, pool.opportunity_id)
        session.commit()
        ids = [s["profile_id"] for s in run.suggestions]
        assert run.ranked_by == "ai"
        assert 1 <= len(ids) <= 10 and len(set(ids)) == len(ids)
        assert set(ids) <= pool.eligible_ids
        assert pool.best_id in ids[:3]
        assert [s["rank"] for s in run.suggestions] == list(range(1, len(ids) + 1))
        assert any(s["reason"] for s in run.suggestions)
        usage = _usage(session)
        assert len(usage) == 1
        row = usage[0]
        assert row.purpose == "shortlist_rank" and row.opportunity_id == pool.opportunity_id
        assert row.workshop_id is None and row.model == get_settings().workshop0_ai_network_model
        assert row.cost_usd > 0 and run.cost_usd == Decimal(str(row.cost_usd))
        stored = session.scalars(
            select(MatchSuggestion).where(MatchSuggestion.run_id == run.run_id).order_by(MatchSuggestion.rank)
        ).all()
        assert [s.profile_id for s in stored] == ids and all(s.ranked_by == "ai" for s in stored)
        assert len(run.run_id) == 22


def test_second_run_keeps_a_new_run_id_and_old_rows(real_ai):
    with create_db_session() as session:
        pool = seed_pool(session)
        first = shortlist_rank.run_shortlist(session, pool.opportunity_id)
        second = shortlist_rank.run_shortlist(session, pool.opportunity_id)
        assert first.run_id != second.run_id
        runs = {r for (r,) in session.execute(select(MatchSuggestion.run_id))}
        assert runs == {first.run_id, second.run_id}
        assert len(_usage(session)) == 2


# --------------------------------------------------------------------------- keyless / failure fallback


@pytest.mark.parametrize("which", ["key", "workspace"])
def test_keyless_ranks_by_rules_in_exact_rule_order_with_no_usage(network_ai_disabled, which):
    network_ai_disabled(which=which)
    with create_db_session() as session:
        pool = seed_pool(session)
        opp = session.get(Opportunity, pool.opportunity_id)
        expected = [c.profile.id for c in matching.eligible(session, opp)][:10]
        run = shortlist_rank.run_shortlist(session, pool.opportunity_id)
        assert run.ranked_by == "rules" and run.cost_usd == Decimal("0")
        assert [s["profile_id"] for s in run.suggestions] == expected
        assert set(expected) <= pool.eligible_ids and expected[0] == pool.best_id
        assert all(s["reason"] is None for s in run.suggestions)
        assert _usage(session) == []


def test_llm_error_falls_back_to_rules_without_raising(monkeypatch):
    def boom(**_kw):
        raise LLMError("http_500", "upstream", status=500)

    monkeypatch.setattr(anthropic_client, "is_available", lambda: True)
    monkeypatch.setattr(anthropic_client, "call_json", boom)
    with create_db_session() as session:
        pool = seed_pool(session)
        run = shortlist_rank.run_shortlist(session, pool.opportunity_id)
        assert run.ranked_by == "rules" and len(run.suggestions) == 10 and run.cost_usd == 0
        assert _usage(session) == []


def test_no_eligible_candidates_returns_an_empty_rules_run(network_ai_disabled):
    network_ai_disabled()
    with create_db_session() as session:
        opp = make_listing(session)
        set_listing_topics(session, opp, ("python",))
        run = shortlist_rank.run_shortlist(session, opp.id)
        assert run.suggestions == [] and run.ranked_by == "rules"


def test_unknown_opportunity_raises_lookup_error():
    with create_db_session() as session:
        with pytest.raises(LookupError):
            shortlist_rank.run_shortlist(session, 999999)


# --------------------------------------------------------------------------- guardrails (no network)


def _candidates(session, n):
    opp = make_listing(session, min_level=None)
    set_listing_topics(session, opp, ("python",))
    for i in range(n):
        make_profile(session, f"Cand {i:02d}", topics={"python": "advanced"}, verified=i == 0)
    return matching.eligible(session, opp)


def test_guardrails_drop_unknown_dupes_blank_reasons_and_cap_and_trim():
    with create_db_session() as session:
        cands = _candidates(session, 14)
        ids = [c.profile.id for c in cands]
        content = {
            "ranking": [
                {"profile_id": 987654, "reason": "not a candidate"},
                {"profile_id": ids[3], "reason": "  strong  "},
                {"profile_id": ids[3], "reason": "duplicate"},
                {"profile_id": ids[4], "reason": "   "},
                {"profile_id": ids[5], "reason": "x" * 500},
                {"profile_id": True, "reason": "bool id"},
                "garbage",
                {"profile_id": str(ids[6]), "reason": "string id"},
            ]
        }
        picks = shortlist_rank.guard_ranking(content, cands)
        assert [p["profile_id"] for p in picks[:2]] == [ids[3], ids[5]]
        assert picks[0]["reason"] == "strong" and len(picks[1]["reason"]) == 300
        assert len(picks) == 10 and len({p["profile_id"] for p in picks}) == 10
        topped = picks[2:]
        assert all(p["reason"] is None for p in topped)
        assert [p["profile_id"] for p in topped] == [i for i in ids if i not in (ids[3], ids[5])][:8]


def test_guardrails_malformed_content_gives_top_by_rule_and_small_pool_is_not_padded():
    with create_db_session() as session:
        cands = _candidates(session, 3)
        for bad in (None, {}, {"ranking": "x"}, {"ranking": None}):
            picks = shortlist_rank.guard_ranking(bad, cands)
            assert [p["profile_id"] for p in picks] == [c.profile.id for c in cands]
        many = {"ranking": [{"profile_id": c.profile.id, "reason": "ok"} for c in cands] * 4}
        assert len(shortlist_rank.guard_ranking(many, cands)) == 3
