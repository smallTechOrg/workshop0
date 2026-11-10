"""C14 trainer side: apply / my applications / withdraw / matches (api.md §Phase 12)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.workshop0.db.models import Application
from tests.integration.applications.conftest import (
    apply_to,
    ctx,
    db,
    make_expired,
    outbox_rows,
)


def test_apply_happy_path_persists_and_queues_received_email(trainer_factory, open_listing):
    user, tclient, pid = trainer_factory("ada@example.test")
    listing = open_listing()
    r = apply_to(tclient, listing["id"], "  I would love to teach this.  ")
    assert r.status_code == 200, r.text
    app = r.json()["data"]["application"]
    assert app["status"] == "applied" and app["source"] == "self"
    assert app["note"] == "I would love to teach this."
    assert app["opportunity"]["public_url"].endswith(f"/opportunities/{listing['slug']}")
    with db() as session:
        row = session.scalar(select(Application))
        assert (row.opportunity_id, row.profile_id, row.status) == (listing["id"], pid, "applied")
    mail = outbox_rows("application.received")
    assert len(mail) == 1 and mail[0].to_email == "ada@example.test"
    c = ctx(mail[0])
    assert c["url"] == f"http://testserver/opportunities/{listing['slug']}"
    assert c["url"].split("/opportunities/")[1] != str(listing["id"])  # slug, never the numeric id
    assert c["applications_url"] == "http://testserver/app/network/applications/"


def test_one_application_per_listing_and_trainer(trainer_factory, open_listing):
    _, tclient, _ = trainer_factory("ada@example.test")
    _, other, _ = trainer_factory("bob@example.test")
    listing = open_listing()
    assert apply_to(tclient, listing["id"]).status_code == 200
    again = apply_to(tclient, listing["id"])
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "already_applied"
    assert apply_to(other, listing["id"]).status_code == 200  # another trainer is fine
    with db() as session:
        assert len(list(session.scalars(select(Application)))) == 2
    assert len(outbox_rows("application.received")) == 2


def test_withdrawn_application_still_blocks_reapply(trainer_factory, open_listing):
    _, tclient, _ = trainer_factory("ada@example.test")
    listing = open_listing()
    app_id = apply_to(tclient, listing["id"]).json()["data"]["application"]["id"]
    assert tclient.post(f"/api/me/applications/{app_id}/withdraw").status_code == 200
    assert apply_to(tclient, listing["id"]).json()["detail"]["code"] == "already_applied"


def test_apply_requires_profile(make_user, signed_in_client, open_listing):
    client_ = signed_in_client(make_user("noprofile@example.test"))
    r = apply_to(client_, open_listing()["id"])
    assert r.status_code == 409 and r.json()["detail"]["code"] == "profile_required"


def test_apply_requires_sign_in_and_csrf(client, make_user, signed_in_client, open_listing):
    listing = open_listing()
    assert client.post("/api/me/applications", json={"opportunity_id": listing["id"]}).status_code == 401
    no_csrf = signed_in_client(make_user("x@example.test"), csrf=False)
    r = no_csrf.post("/api/me/applications", json={"opportunity_id": listing["id"]})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "csrf_failed"


def test_opportunity_closed_for_closed_and_expired(client, admin_headers, trainer_factory, open_listing):
    _, tclient, _ = trainer_factory("ada@example.test")
    closed = open_listing()
    assert client.patch(
        f"/api/admin/opportunities/{closed['id']}", json={"status": "closed"}, headers=admin_headers
    ).status_code == 200
    expired = open_listing(title="Expiring soon workshop")
    make_expired(expired["id"])
    for opp in (closed, expired):
        r = apply_to(tclient, opp["id"])
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "opportunity_closed"
    with db() as session:
        assert session.scalar(select(Application)) is None
    assert outbox_rows("application.received") == []


@pytest.mark.parametrize("bad_id", [0, -5, 999999, 2**40])
def test_apply_unknown_listing_404(trainer_factory, bad_id):
    _, tclient, _ = trainer_factory("ada@example.test")
    r = apply_to(tclient, bad_id)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "not_found"


def test_apply_to_draft_is_not_found(trainer_factory, create_opportunity):
    _, tclient, _ = trainer_factory("ada@example.test")
    draft = create_opportunity()  # default status draft
    assert apply_to(tclient, draft["id"]).status_code == 404


def test_apply_validation(trainer_factory, open_listing):
    _, tclient, _ = trainer_factory("ada@example.test")
    listing = open_listing()
    assert tclient.post("/api/me/applications", json={}).status_code == 422
    assert tclient.post("/api/me/applications", json={"opportunity_id": "abc"}).status_code == 422
    too_long = apply_to(tclient, listing["id"], "x" * 1001)
    assert too_long.status_code == 422
    boundary = apply_to(tclient, listing["id"], "y" * 1000)
    assert boundary.status_code == 200 and len(boundary.json()["data"]["application"]["note"]) == 1000


def test_blank_note_stored_as_null(trainer_factory, open_listing):
    _, tclient, _ = trainer_factory("ada@example.test")
    r = apply_to(tclient, open_listing()["id"], "   ")
    assert r.json()["data"]["application"]["note"] is None


def test_apply_rate_limit_30_per_hour(trainer_factory, open_listing):
    _, tclient, _ = trainer_factory("ada@example.test")
    ids = [open_listing(title=f"Listing number {i} for rate test")["id"] for i in range(31)]
    codes = [apply_to(tclient, i).status_code for i in ids]
    assert codes[:30] == [200] * 30 and codes[30] == 429


def test_invited_source_when_opportunity_invite_exists(trainer_factory, open_listing):
    from src.workshop0.db.models import OpportunityInvite

    _, tclient, pid = trainer_factory("ada@example.test")
    listing = open_listing()
    with db() as session:
        session.add(OpportunityInvite(opportunity_id=listing["id"], profile_id=pid, created_by="admin"))
        session.commit()
    r = apply_to(tclient, listing["id"])
    assert r.json()["data"]["application"]["source"] == "invited"


def test_my_applications_newest_first_with_cards_and_state_survives(
    trainer_factory, open_listing, make_app, signed_in_client
):
    user, tclient, _ = trainer_factory("ada@example.test")
    empty = tclient.get("/api/me/applications").json()["data"]
    assert empty == {"applications": []}
    first, second = open_listing(title="First listing here"), open_listing(title="Second listing here")
    apply_to(tclient, first["id"], "one")
    apply_to(tclient, second["id"], "two")
    data = tclient.get("/api/me/applications").json()["data"]["applications"]
    assert [a["opportunity"]["title"] for a in data] == ["Second listing here", "First listing here"]
    for a in data:
        assert a["status_changed_at"].endswith("Z")
        assert set(a["opportunity"]) >= {"slug", "title", "public_url", "status", "deadline"}
    # state survives a brand-new app + session
    fresh = signed_in_client(user)
    assert len(fresh.get("/api/me/applications").json()["data"]["applications"]) == 2


def test_my_applications_without_profile_is_empty(make_user, signed_in_client):
    client_ = signed_in_client(make_user("np@example.test"))
    assert client_.get("/api/me/applications").json()["data"] == {"applications": []}


def test_my_applications_never_leak_admin_fields(trainer_factory, open_listing):
    _, tclient, _ = trainer_factory("ada@example.test")
    listing = open_listing(budget_min=100, budget_max=500, budget_currency="INR", budget_unit="day",
                           min_level="expert")
    apply_to(tclient, listing["id"])
    raw = tclient.get("/api/me/applications").text
    for needle in ("budget_", "min_level", "internal_notes", "partner_internal_name", "stored_status"):
        assert needle not in raw


def test_withdraw_from_applied_and_shortlisted(client, admin_headers, trainer_factory, open_listing):
    _, tclient, _ = trainer_factory("ada@example.test")
    listing = open_listing()
    app_id = apply_to(tclient, listing["id"]).json()["data"]["application"]["id"]
    r = tclient.post(f"/api/me/applications/{app_id}/withdraw")
    assert r.status_code == 200 and r.json()["data"]["application"]["status"] == "withdrawn"
    assert tclient.post(f"/api/me/applications/{app_id}/withdraw").json()["detail"]["code"] == "cannot_withdraw"

    _, t2, _ = trainer_factory("bob@example.test")
    app2 = apply_to(t2, listing["id"]).json()["data"]["application"]["id"]
    move = client.post(
        f"/api/admin/opportunities/{listing['id']}/applications/status",
        json={"application_ids": [app2], "status": "shortlisted", "notify": False},
        headers=admin_headers,
    )
    assert move.status_code == 200
    assert t2.post(f"/api/me/applications/{app2}/withdraw").status_code == 200


def test_withdraw_refused_after_selected(client, admin_headers, trainer_factory, open_listing):
    _, tclient, _ = trainer_factory("ada@example.test")
    listing = open_listing()
    app_id = apply_to(tclient, listing["id"]).json()["data"]["application"]["id"]
    client.post(
        f"/api/admin/opportunities/{listing['id']}/applications/status",
        json={"application_ids": [app_id], "status": "selected", "notify": False},
        headers=admin_headers,
    )
    r = tclient.post(f"/api/me/applications/{app_id}/withdraw")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "cannot_withdraw"


def test_cannot_withdraw_someone_elses_application(trainer_factory, open_listing):
    _, a, _ = trainer_factory("ada@example.test")
    _, b, _ = trainer_factory("bob@example.test")
    app_id = apply_to(a, open_listing()["id"]).json()["data"]["application"]["id"]
    r = b.post(f"/api/me/applications/{app_id}/withdraw")
    assert r.status_code == 404
    assert b.post("/api/me/applications/99999/withdraw").status_code == 404


def test_matches_uses_matching_service_and_flags_invited(trainer_factory, open_listing, monkeypatch):
    """matching.matches_for is B2's; the stub is replaced here (route shape + serialisation)."""
    from src.workshop0.db.models import Opportunity
    from src.workshop0.services import matching

    _, tclient, _ = trainer_factory("ada@example.test")
    a, b = open_listing(title="Listing A for matching"), open_listing(title="Listing B for matching")
    seen = {}

    def fake(session, profile, limit=10):
        seen["limit"] = limit
        opps = {o.id: o for o in session.scalars(select(Opportunity))}
        return [
            matching.Match(opportunity=opps[b["id"]], rule_score=0.91234, invited=True),
            matching.Match(opportunity=opps[a["id"]], rule_score=0.5, invited=False),
        ]

    monkeypatch.setattr(matching, "matches_for", fake)
    r = tclient.get("/api/me/matches")
    assert r.status_code == 200, r.text
    items = r.json()["data"]["matches"]
    assert seen["limit"] == 10
    assert [(m["opportunity"]["title"], m["invited"], m["rule_score"]) for m in items] == [
        ("Listing B for matching", True, 0.912),
        ("Listing A for matching", False, 0.5),
    ]
    for needle in ("budget_", "min_level", "internal_notes"):
        assert needle not in r.text


def test_matches_requires_profile_and_signin(client, make_user, signed_in_client):
    assert client.get("/api/me/matches").status_code == 401
    r = signed_in_client(make_user("np@example.test")).get("/api/me/matches")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "profile_required"
