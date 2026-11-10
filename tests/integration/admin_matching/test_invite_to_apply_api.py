"""POST /api/admin/opportunities/{id}/invites (spec/api.md §Phase 12)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from src.workshop0.db.models import EmailOutbox, FacilitatorAction, Opportunity, OpportunityInvite
from src.workshop0.db.session import create_db_session
from src.workshop0.services import matching
from tests.fixtures.network_pool import make_listing, make_profile, seed_pool, set_listing_topics


def _url(oid: int) -> str:
    return f"/api/admin/opportunities/{oid}/invites"


def _outbox() -> list[EmailOutbox]:
    with create_db_session() as session:
        return list(session.scalars(select(EmailOutbox).order_by(EmailOutbox.id)))


def test_requires_admin(client):
    with create_db_session() as session:
        pool = seed_pool(session)
    assert client.post(_url(pool.opportunity_id), json={"profile_ids": [pool.best_id]}).status_code == 401


def test_invite_creates_rows_emails_with_slug_link_and_one_audit(client, admin_headers):
    with create_db_session() as session:
        pool = seed_pool(session)
        slug = session.get(Opportunity, pool.opportunity_id).slug
    ids = [pool.best_id, sorted(pool.eligible_ids - {pool.best_id})[0]]
    r = client.post(_url(pool.opportunity_id), json={"profile_ids": ids}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert [(i["profile_id"], i["created"], i["email"]) for i in r.json()["data"]["invites"]] == [
        (ids[0], True, "queued"), (ids[1], True, "queued")
    ]
    with create_db_session() as session:
        assert matching.invited_profile_ids(session, pool.opportunity_id) == set(ids)
        audits = list(session.scalars(select(FacilitatorAction).where(FacilitatorAction.action == "opportunity.invite")))
        assert len(audits) == 1 and audits[0].subject_id == pool.opportunity_id
        assert json.loads(audits[0].detail_json)["profile_ids"] == ids
    rows = _outbox()
    assert len(rows) == 2 and {r.template for r in rows} == {"opportunity.invite"}
    assert {r.dedupe_key for r in rows} == {f"opp-invite:{pool.opportunity_id}:{i}" for i in ids}
    ctx = json.loads(rows[0].context_json)
    assert ctx["url"] == f"/opportunities/{slug}" or ctx["url"].endswith(f"/opportunities/{slug}")
    assert ctx["title"] == "GenAI bootcamp" and ctx["partner"] == "A Pune edtech"
    assert "Zenvia" not in rows[0].context_json
    assert ctx["cities"] == "Pune, Bengaluru"
    assert "10,000" in ctx["compensation"] and "per day" in ctx["compensation"]
    assert {r.to_email for r in rows} == {pool.user_emails[i] for i in ids}


def test_rerun_is_idempotent_one_row_one_email_per_trainer(client, admin_headers):
    with create_db_session() as session:
        pool = seed_pool(session)
    body = {"profile_ids": [pool.best_id, pool.best_id]}
    first = client.post(_url(pool.opportunity_id), json=body, headers=admin_headers).json()["data"]["invites"]
    again = client.post(_url(pool.opportunity_id), json=body, headers=admin_headers).json()["data"]["invites"]
    assert len(first) == 1 and first[0]["created"] is True and again[0]["created"] is False
    assert len(_outbox()) == 1
    with create_db_session() as session:
        assert len(list(session.scalars(select(OpportunityInvite)))) == 1


def test_validation_and_state_errors(client, admin_headers):
    with create_db_session() as session:
        pool = seed_pool(session)
        draft = make_listing(session, slug="draft-one", status="draft")
        expired = make_listing(session, slug="expired-one", deadline=datetime.now(timezone.utc) - timedelta(days=1))
        draft_id, expired_id = draft.id, expired.id
    url = _url(pool.opportunity_id)
    for body, code in (({"profile_ids": []}, "validation_error"), ({"profile_ids": [999999]}, "validation_error"),
                       ({"profile_ids": list(range(1, 52))}, "validation_error")):
        r = client.post(url, json=body, headers=admin_headers)
        assert r.status_code == 422 and r.json()["detail"]["code"] == code, body
    assert client.post(url, json={}, headers=admin_headers).status_code == 422
    assert client.post(_url(999999), json={"profile_ids": [pool.best_id]}, headers=admin_headers).status_code == 404
    for oid in (draft_id, expired_id):
        r = client.post(_url(oid), json={"profile_ids": [pool.best_id]}, headers=admin_headers)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "opportunity_closed"
    assert _outbox() == []


def test_invited_flag_shows_in_shortlist_and_matched_for_you(client, admin_headers, network_ai_disabled):
    network_ai_disabled()
    with create_db_session() as session:
        pool = seed_pool(session)
    client.post(_url(pool.opportunity_id), json={"profile_ids": [pool.best_id]}, headers=admin_headers)
    data = client.post(f"/api/admin/opportunities/{pool.opportunity_id}/shortlist", headers=admin_headers).json()["data"]
    flags = {s["trainer"]["id"]: s["invited"] for s in data["suggestions"]}
    assert flags[pool.best_id] is True and sum(flags.values()) == 1
