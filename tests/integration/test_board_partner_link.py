"""F3 — opportunity <-> partner link: partner_id / legacy partner_internal_name,
mirror, audit, `q` join (PostgreSQL)."""

from sqlalchemy import text

from tests.conftest import opportunity_body


def _partner(client, headers, name, **extra):
    response = client.post(
        "/api/admin/partners", json={"internal_name": name, **extra}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["partner"]


def _create(client, headers, topic_id=1, **over):
    """POST a listing without the fixture's default legacy partner name (an explicit null
    next to a partner_id is a clear that conflicts)."""
    body = opportunity_body([topic_id], **over)
    if "partner_internal_name" not in over:
        body.pop("partner_internal_name")
    return client.post("/api/admin/opportunities", json=body, headers=headers)


def _patch(client, headers, opp_id, **body):
    return client.patch(f"/api/admin/opportunities/{opp_id}", json=body, headers=headers)


def _scalar(sql, **params):
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        return session.execute(text(sql), params).scalar_one()


def _mirror(opp_id):
    return _scalar("select partner_internal_name from opportunity where id=:i", i=opp_id)


def _action_count(action):
    return _scalar("select count(*) from facilitator_action where action=:a", a=action)


def test_partner_id_set_changed_cleared_with_mirror(client, admin_headers, create_opportunity):
    a = _partner(client, admin_headers, "Link Alpha Co")
    b = _partner(client, admin_headers, "Link Beta Co", notes="secret note")
    created = _create(client, admin_headers, partner_id=a["id"])
    assert created.status_code == 200, created.text
    opp = created.json()["data"]["opportunity"]
    assert opp["partner_id"] == a["id"]
    assert opp["partner"] == {
        "id": a["id"], "internal_name": "Link Alpha Co", "display_name": None, "active": True,
    }
    assert opp["partner_internal_name"] == "Link Alpha Co" and _mirror(opp["id"]) == "Link Alpha Co"

    changed = _patch(client, admin_headers, opp["id"], partner_id=b["id"]).json()["data"]["opportunity"]
    assert changed["partner_id"] == b["id"] and changed["partner_internal_name"] == "Link Beta Co"
    assert "notes" not in changed["partner"] and _mirror(opp["id"]) == "Link Beta Co"
    activity = client.get(f"/api/admin/opportunities/{opp['id']}", headers=admin_headers).json()["data"]["activity"]
    assert activity[0]["detail"]["changed_fields"] == ["partner_id"]

    cleared = _patch(client, admin_headers, opp["id"], partner_id=None).json()["data"]["opportunity"]
    assert cleared["partner_id"] is None and cleared["partner"] is None
    assert cleared["partner_internal_name"] is None and _mirror(opp["id"]) is None


def test_unknown_inactive_and_kept_inactive_partner(client, admin_headers, create_opportunity):
    opp = create_opportunity(partner_internal_name=None)
    bad = _patch(client, admin_headers, opp["id"], partner_id=999999)
    assert bad.status_code == 422
    assert bad.json()["detail"]["message"] == "partner_id: partner 999999 does not exist"

    p = _partner(client, admin_headers, "Link Gamma Co")
    attached = _patch(client, admin_headers, opp["id"], partner_id=p["id"])
    assert attached.status_code == 200
    client.patch(f"/api/admin/partners/{p['id']}", json={"active": False}, headers=admin_headers)

    # already attached: kept (re-sending the same id and unrelated edits are fine)
    assert _patch(client, admin_headers, opp["id"], partner_id=p["id"], summary="Edited").status_code == 200
    # a new attachment of an inactive partner is refused
    other = create_opportunity(partner_internal_name=None)
    refused = _patch(client, admin_headers, other["id"], partner_id=p["id"])
    assert refused.status_code == 422
    assert refused.json()["detail"]["message"] == "partner_id: partner is inactive"
    refused_create = _create(client, admin_headers, partner_id=p["id"])
    assert refused_create.status_code == 422


def test_legacy_name_reuses_case_variant_or_creates_partner_with_audit(
    client, admin_headers, create_opportunity
):
    existing = _partner(client, admin_headers, "Legacy Delta Ltd")
    before = _action_count("partner.create")
    opp = create_opportunity(partner_internal_name="  legacy   DELTA ltd ")
    assert opp["partner_id"] == existing["id"]
    assert _action_count("partner.create") == before

    fresh = create_opportunity(partner_internal_name="Brand New Org", partner_display_name="A new org")
    assert fresh["partner_id"] != existing["id"]
    assert fresh["partner"]["internal_name"] == "Brand New Org"
    assert fresh["partner"]["display_name"] == "A new org"
    assert _action_count("partner.create") == before + 1
    assert _mirror(fresh["id"]) == "Brand New Org"

    cleared = _patch(client, admin_headers, fresh["id"], partner_internal_name=None)
    assert cleared.json()["data"]["opportunity"]["partner_id"] is None


def test_conflicting_id_and_name_is_validation_error_and_creates_nothing(
    client, admin_headers, create_opportunity
):
    a = _partner(client, admin_headers, "Conflict One Co")
    _partner(client, admin_headers, "Conflict Two Co")
    opp = create_opportunity(partner_internal_name=None)
    before = _scalar("select count(*) from partner")
    response = _patch(
        client, admin_headers, opp["id"], partner_id=a["id"], partner_internal_name="Conflict Two Co"
    )
    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "partner_id: conflicts with partner_internal_name"
    unmatched = _patch(
        client, admin_headers, opp["id"], partner_id=a["id"], partner_internal_name="Nobody Matches"
    )
    assert unmatched.status_code == 422
    assert _scalar("select count(*) from partner") == before


def test_same_legacy_name_is_a_no_op_and_rejected_write_creates_no_partner(
    client, admin_headers, create_opportunity
):
    opp = create_opportunity(partner_internal_name="Noop Partner Inc")
    audits = _scalar("select count(*) from facilitator_action")
    same = _patch(client, admin_headers, opp["id"], partner_internal_name="noop partner inc")
    assert same.status_code == 200
    assert _scalar("select count(*) from facilitator_action") == audits

    partners = _scalar("select count(*) from partner")
    bad = _patch(client, admin_headers, opp["id"], title="x", partner_internal_name="Should Not Exist")
    assert bad.status_code == 422
    assert _scalar("select count(*) from partner") == partners


def test_audit_by_is_admin_actor_for_opportunity_and_topic_writes(
    client, admin_headers, create_opportunity
):
    opp = create_opportunity()
    client.post("/api/admin/topics", json={"name": "Zig Lang", "category": "Languages"}, headers=admin_headers)
    rows = _scalar(
        "select count(*) from facilitator_action where action in ('opportunity.create','topic.create') "
        "and detail_json like '%\"by\": \"admin-key\"%'"
    )
    assert rows >= 2 and opp["id"]


def test_q_matches_partner_internal_name_through_join_and_follows_rename(
    client, admin_headers, create_opportunity
):
    p = _partner(client, admin_headers, "Qjoin Original Name")
    opp = _create(client, admin_headers, partner_id=p["id"]).json()["data"]["opportunity"]
    renamed = client.patch(
        f"/api/admin/partners/{p['id']}", json={"internal_name": "Zyxwv Renamed Corp"}, headers=admin_headers
    )
    assert renamed.status_code == 200
    found = client.get("/api/admin/opportunities", params={"q": "zyxwv renamed"}, headers=admin_headers)
    data = found.json()["data"]
    assert [o["id"] for o in data["opportunities"]] == [opp["id"]] and data["total"] == 1
    assert data["opportunities"][0]["partner_internal_name"] == "Zyxwv Renamed Corp"
    gone = client.get("/api/admin/opportunities", params={"q": "qjoin original"}, headers=admin_headers)
    assert gone.json()["data"]["total"] == 0
