"""Rule prefilter, rule score, matches_for (spec/agent.md §Shortlist ranker step 1). PostgreSQL."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from src.workshop0.db.models import Opportunity, OpportunityInvite, TrainerProfile
from src.workshop0.db.session import create_db_session
from src.workshop0.services import matching
from tests.fixtures.network_pool import (
    ELIGIBLE_COUNT,
    make_listing,
    make_profile,
    seed_pool,
    set_listing_topics,
)


def _eligible_ids(session, opp_id, **kw):
    opp = session.get(Opportunity, opp_id)
    return [c.profile.id for c in matching.eligible(session, opp, **kw)]


# --------------------------------------------------------------------------- happy path


def test_eligible_set_is_exactly_the_precomputed_17_and_best_ranks_first():
    with create_db_session() as session:
        pool = seed_pool(session)
        opp = session.get(Opportunity, pool.opportunity_id)
        candidates = matching.eligible(session, opp)
        ids = [c.profile.id for c in candidates]
        assert len(ids) == ELIGIBLE_COUNT == 17
        assert set(ids) == pool.eligible_ids
        assert ids[0] == pool.best_id
        scores = [c.rule_score for c in candidates]
        assert scores == sorted(scores, reverse=True)
        assert all(0.0 <= s <= 1.0 for s in scores)


def test_each_rule_removes_exactly_its_group():
    with create_db_session() as session:
        pool = seed_pool(session)
        got = set(_eligible_ids(session, pool.opportunity_id))
        for reason, ids in pool.by_reason.items():
            assert ids and not (got & ids), reason
        # the admin-only budget step is skippable (Matched for you): only the rate group returns
        without_budget = set(_eligible_ids(session, pool.opportunity_id, include_budget=False))
        assert without_budget == pool.eligible_ids | pool.by_reason["rate"]


def test_rule_score_formula_for_the_best_trainer():
    with create_db_session() as session:
        pool = seed_pool(session)
        opp = session.get(Opportunity, pool.opportunity_id)
        best = session.get(TrainerProfile, pool.best_id)
        # coverage 1.0 (expert x3), verified 1.0, listing weekdays {mon,tue} fully available (1.0)
        completeness = matching._profile_contexts(session, [best])[0].completeness_fraction()
        expected = round(0.5 + 0.2 + 0.15 * completeness + 0.15, 6)
        assert matching.rule_score(best, opp) == expected
        assert 0.85 < expected < 1.0


def test_topic_level_weights_decide_coverage():
    with create_db_session() as session:
        opp = make_listing(session, min_level=None, starts_on=None, ends_on=None, budget_max=None,
                           budget_currency=None, budget_unit=None, compensation_max=None, compensation_min=None,
                           compensation_currency=None, compensation_unit=None, location_mode="remote", locations_json="[]")
        set_listing_topics(session, opp, ("python", "kubernetes"))
        a = make_profile(session, "Adv One", topics={"python": "advanced", "kubernetes": "intermediate"})
        e = make_profile(session, "Exp Two", topics={"python": "expert", "kubernetes": "expert"})
        by = {c.profile.id: c.rule_score for c in matching.eligible(session, opp)}
        # 0.5 * (0.8 + 0.6) / 2 vs 0.5 * 1.0; the remaining terms are identical
        assert round(by[e.id] - by[a.id], 6) == round(0.5 * (1.0 - 0.7), 6)


# --------------------------------------------------------------------------- edge cases


def test_multi_city_onsite_listing_matches_a_trainer_in_any_listed_city():
    with create_db_session() as session:
        opp = make_listing(session)
        set_listing_topics(session, opp, ("python",))
        pune = make_profile(session, "In Pune", topics={"python": "advanced"}, city="PUNE")
        blr = make_profile(session, "In Bengaluru", topics={"python": "advanced"}, city=" bengaluru ")
        chn = make_profile(session, "In Chennai", topics={"python": "advanced"}, city="Chennai", remote_ok=True)
        assert {pune.id, blr.id} == set(_eligible_ids(session, opp.id))
        assert chn.id not in _eligible_ids(session, opp.id)


def test_hybrid_allows_remote_ok_and_remote_ignores_city():
    with create_db_session() as session:
        hybrid = make_listing(session, slug="hybrid", location_mode="hybrid")
        remote = make_listing(session, slug="remote", location_mode="remote", locations_json="[]", city=None)
        for o in (hybrid, remote):
            set_listing_topics(session, o, ("python",))
        far = make_profile(session, "Far Remote", topics={"python": "advanced"}, city="Chennai", remote_ok=True)
        stuck = make_profile(session, "Far Onsite", topics={"python": "advanced"}, city="Chennai", remote_ok=False)
        assert far.id in _eligible_ids(session, hybrid.id) and stuck.id not in _eligible_ids(session, hybrid.id)
        assert {far.id, stuck.id} <= set(_eligible_ids(session, remote.id))


def test_budget_falls_back_to_public_compensation_and_pro_bono_always_fits():
    with create_db_session() as session:
        opp = make_listing(session, budget_max=None, budget_currency=None, budget_unit=None,
                           compensation_max=5000, compensation_currency="INR", compensation_unit="day")
        set_listing_topics(session, opp, ("python",))
        cheap = make_profile(session, "Cheap", topics={"python": "advanced"}, rate=(5000, "INR", "day"))
        dear = make_profile(session, "Dear", topics={"python": "advanced"}, rate=(5001, "INR", "day"))
        free = make_profile(session, "Free", topics={"python": "advanced"}, rate=None, pro_bono=True)
        got = set(_eligible_ids(session, opp.id))
        assert cheap.id in got and free.id in got and dear.id not in got


def test_no_dates_and_no_topics_listing_never_filters_on_them_and_overlap_is_one():
    with create_db_session() as session:
        opp = make_listing(session, starts_on=None, ends_on=None, location_mode="remote", locations_json="[]",
                           min_level=None, budget_max=None, budget_currency=None, budget_unit=None,
                           compensation_max=None, compensation_min=None, compensation_currency=None, compensation_unit=None)
        set_listing_topics(session, opp, ("python",))
        p = make_profile(session, "Anytime", topics={"python": "intermediate"}, available_from=date(2030, 1, 1),
                         blackouts=[("2020-01-01", "2040-01-01")], availability={})
        assert _eligible_ids(session, opp.id) == [p.id]
        (c,) = matching.eligible(session, opp)
        ctx = matching._profile_contexts(session, [p])[0]
        assert c.rule_score == round(0.5 * 0.6 + 0.15 * ctx.completeness_fraction() + 0.15, 6)


def test_ties_break_by_updated_at_desc_then_id():
    with create_db_session() as session:
        opp = make_listing(session, min_level=None)
        set_listing_topics(session, opp, ("python",))
        now = datetime.now(timezone.utc)
        old = make_profile(session, "Old", topics={"python": "advanced"}, updated_at=now - timedelta(days=3))
        new = make_profile(session, "New", topics={"python": "advanced"}, updated_at=now)
        same_a = make_profile(session, "Same A", topics={"python": "advanced"}, updated_at=now - timedelta(days=1))
        same_b = make_profile(session, "Same B", topics={"python": "advanced"}, updated_at=now - timedelta(days=1))
        order = _eligible_ids(session, opp.id)
        assert order == [new.id, same_a.id, same_b.id, old.id]


def test_empty_pool_yields_no_candidates():
    with create_db_session() as session:
        opp = make_listing(session)
        set_listing_topics(session, opp, ("python",))
        assert matching.eligible(session, opp) == []


# --------------------------------------------------------------------------- matches_for


def test_matches_for_ranks_three_listings_in_the_precomputed_order_invited_first():
    with create_db_session() as session:
        base = dict(location_mode="remote", locations_json="[]", city=None, starts_on=None, ends_on=None)
        full = make_listing(session, slug="full", **base)
        half = make_listing(session, slug="half", **base)
        weak = make_listing(session, slug="weak", **base)
        set_listing_topics(session, full, ("python", "kubernetes"))   # coverage (1.0 + 1.0) / 2
        set_listing_topics(session, half, ("python", "generative-ai"))  # coverage (1.0 + 0) / 2
        set_listing_topics(session, weak, ("kubernetes", "generative-ai", "react"))  # 1/3 ... but level gate
        me = make_profile(session, "Me", topics={"python": "expert", "kubernetes": "expert", "react": "advanced"})
        # listing without any topic the trainer holds is dropped by the prefilter
        other = make_listing(session, slug="other", **base)
        set_listing_topics(session, other, ("ux-design",))
        order = [m.opportunity.slug for m in matching.matches_for(session, me)]
        assert order == ["full", "weak", "half"]
        assert all(not m.invited for m in matching.matches_for(session, me))

        session.add(OpportunityInvite(opportunity_id=other.id, profile_id=me.id, created_by="admin"))
        session.flush()
        matches = matching.matches_for(session, me)
        assert [m.opportunity.slug for m in matches] == ["other", "full", "weak", "half"]
        assert [m.invited for m in matches] == [True, False, False, False]
        assert len(matching.matches_for(session, me, limit=2)) == 2


def test_matches_for_skips_closed_expired_and_draft_listings():
    with create_db_session() as session:
        base = dict(location_mode="remote", locations_json="[]", city=None, starts_on=None, ends_on=None)
        live = make_listing(session, slug="live", **base)
        past = make_listing(session, slug="past", deadline=datetime.now(timezone.utc) - timedelta(days=1), **base)
        closed = make_listing(session, slug="closed", status="closed", **base)
        draft = make_listing(session, slug="draft", status="draft", **base)
        for o in (live, past, closed, draft):
            set_listing_topics(session, o, ("python",))
        me = make_profile(session, "Me", topics={"python": "advanced"})
        assert [m.opportunity.slug for m in matching.matches_for(session, me)] == ["live"]
