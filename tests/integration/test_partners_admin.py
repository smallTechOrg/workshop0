"""Phase 11b F2 — admin partner list (spec/api.md §Phase 11b): CRUD, normalised uniqueness,
deactivate, opportunity_count, mirror rewrite, audit rows, auth/CSRF, resolve_partner (PostgreSQL)."""

import json

import pytest
from sqlalchemy import text

from src.workshop0.services.partners import PARTNER_EXISTS_MESSAGE, normalize_name

URL = "/api/admin/partners"


def _rows(sql: str, **params) -> list:
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        return list(session.execute(text(sql), params).mappings())


def _audit(action: str) -> list[dict]:
    rows = _rows(
        "SELECT actor, workshop_id, subject_type, subject_id, detail_json FROM facilitator_action "
        "WHERE action = :a ORDER BY id",
        a=action,
    )
    return [{**r, "detail": json.loads(r["detail_json"])} for r in rows]


def _create(client, headers, name="Zenvia Learning Pvt Ltd", **extra) -> dict:
    response = client.post(URL, json={"internal_name": name, **extra}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]["partner"]


def _attach(opportunity_id: int, partner_id: int, mirror: str) -> None:
    """Link a listing to a partner directly (the opportunity writer is F3's slice)."""
    from tests.conftest import db_execute

    db_execute(
        "UPDATE opportunity SET partner_id = :p, partner_internal_name = :m WHERE id = :o",
        p=partner_id, m=mirror, o=opportunity_id,
    )


ADMIN_PARTNER_KEYS = {
    "id", "internal_name", "display_name", "notes", "active", "opportunity_count",
    "created_at", "updated_at",
}


# --------------------------------------------------------------------------- normalize


def test_normalize_name_collapses_and_casefolds():
    assert normalize_name("  Acme   Payments\tPvt  Ltd ") == ("Acme Payments Pvt Ltd", "acme payments pvt ltd")
    assert normalize_name("Straße")[1] == "strasse"
    assert normalize_name("   ") == ("", "")


# --------------------------------------------------------------------------- auth


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", URL, None),
        ("post", URL, {"internal_name": "Acme"}),
        ("patch", f"{URL}/1", {"active": False}),
    ],
)
@pytest.mark.parametrize("key", [None, "wrong-key"])
def test_partner_endpoints_require_the_admin_key(client, method, path, body, key):
    headers = {"X-Admin-Key": key} if key else {}
    kwargs = {"json": body} if body is not None else {}
    response = getattr(client, method)(path, headers=headers, **kwargs)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_admin_key"
    assert _rows("SELECT count(*) AS n FROM partner")[0]["n"] == 0


def test_session_admin_can_manage_partners_and_audit_carries_their_email(
    client, make_user, signed_in_client
):
    admin = make_user("boss@example.test", admin=True)
    admin_client = signed_in_client(admin)
    response = admin_client.post(URL, json={"internal_name": "Acme"})
    assert response.status_code == 200, response.text
    assert admin_client.get(URL).status_code == 200
    assert _audit("partner.create")[0]["detail"]["by"] == "boss@example.test"


def test_session_admin_mutation_without_csrf_is_refused(make_user, signed_in_client):
    admin = make_user("boss@example.test", admin=True)
    admin_client = signed_in_client(admin, csrf=False)
    response = admin_client.post(URL, json={"internal_name": "Acme"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "csrf_failed"
    assert _rows("SELECT count(*) AS n FROM partner")[0]["n"] == 0


def test_non_admin_session_is_refused(make_user, signed_in_client):
    user = make_user("plain@example.test")
    response = signed_in_client(user).get(URL)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "not_admin"


# --------------------------------------------------------------------------- create / list


def test_create_returns_admin_shape_persists_and_audits(client, admin_headers):
    partner = _create(
        client, admin_headers, "  Zenvia   Learning Pvt Ltd ",
        display_name=" A Pune edtech ", notes="Contact: P. Nair",
    )
    assert set(partner) == ADMIN_PARTNER_KEYS
    assert partner["internal_name"] == "Zenvia Learning Pvt Ltd"
    assert partner["display_name"] == "A Pune edtech"
    assert partner["active"] is True and partner["opportunity_count"] == 0
    row = _rows("SELECT internal_name, name_key, notes, active FROM partner")[0]
    assert row["name_key"] == "zenvia learning pvt ltd" and row["notes"] == "Contact: P. Nair"
    (audit,) = _audit("partner.create")
    assert audit["actor"] == "admin" and audit["workshop_id"] is None
    assert audit["subject_type"] == "partner" and audit["subject_id"] == partner["id"]
    assert audit["detail"] == {"internal_name": "Zenvia Learning Pvt Ltd", "by": "admin-key"}


def test_create_blank_optionals_become_null(client, admin_headers):
    partner = _create(client, admin_headers, "Acme", display_name="   ", notes="")
    assert partner["display_name"] is None and partner["notes"] is None


@pytest.mark.parametrize("variant", ["acme payments", "ACME  PAYMENTS", "  Acme\tPayments "])
def test_duplicate_normalised_name_is_409_and_creates_no_row(client, admin_headers, variant):
    _create(client, admin_headers, "Acme Payments")
    response = client.post(URL, json={"internal_name": variant}, headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "partner_exists", "message": PARTNER_EXISTS_MESSAGE}
    assert _rows("SELECT count(*) AS n FROM partner")[0]["n"] == 1
    assert len(_audit("partner.create")) == 1


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ({}, "internal_name"),
        ({"internal_name": "A"}, "internal_name: must be 2 to 160 characters"),
        ({"internal_name": "   "}, "internal_name: must be 2 to 160 characters"),
        ({"internal_name": "x" * 161}, "internal_name: must be 2 to 160 characters"),
        ({"internal_name": "Acme", "display_name": "d" * 161}, "display_name: must be at most 160"),
        ({"internal_name": "Acme", "notes": "n" * 5001}, "notes: must be at most 5000"),
    ],
)
def test_create_validation_errors(client, admin_headers, body, fragment):
    response = client.post(URL, json=body, headers=admin_headers)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "validation_error" and fragment in detail["message"]
    assert _rows("SELECT count(*) AS n FROM partner")[0]["n"] == 0


def test_create_boundary_name_lengths_accepted(client, admin_headers):
    assert _create(client, admin_headers, "AB")["internal_name"] == "AB"
    assert len(_create(client, admin_headers, "x" * 160)["internal_name"]) == 160


def test_list_orders_by_name_key_includes_inactive_and_counts_listings(
    client, admin_headers, create_opportunity
):
    beta = _create(client, admin_headers, "beta Corp")
    alpha = _create(client, admin_headers, "Alpha Corp")
    client.patch(f"{URL}/{beta['id']}", json={"active": False}, headers=admin_headers)
    assert client.get(URL, headers=admin_headers).json()["data"]["partners"][0]["id"] == alpha["id"]
    for status in ("draft", "draft", "closed"):
        _attach(create_opportunity(status=status)["id"], alpha["id"], "Alpha Corp")
    partners = client.get(URL, headers=admin_headers).json()["data"]["partners"]
    assert [p["internal_name"] for p in partners] == ["Alpha Corp", "beta Corp"]
    assert [p["opportunity_count"] for p in partners] == [3, 0]
    assert [p["active"] for p in partners] == [True, False]
    assert all(set(p) == ADMIN_PARTNER_KEYS for p in partners)


def test_list_empty(client, admin_headers):
    assert client.get(URL, headers=admin_headers).json()["data"] == {"partners": []}


# --------------------------------------------------------------------------- patch


def test_patch_fields_deactivate_reactivate_and_single_audit_row(client, admin_headers):
    p = _create(client, admin_headers, "Acme", display_name="Old", notes="n")
    response = client.patch(
        f"{URL}/{p['id']}",
        json={"display_name": "A fintech", "notes": None, "active": False},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    updated = response.json()["data"]["partner"]
    assert updated["display_name"] == "A fintech" and updated["notes"] is None
    assert updated["active"] is False and updated["internal_name"] == "Acme"
    (audit,) = _audit("partner.update")
    assert audit["subject_type"] == "partner" and audit["subject_id"] == p["id"]
    assert audit["actor"] == "admin" and audit["detail"]["by"] == "admin-key"
    assert sorted(audit["detail"]["changed_fields"]) == ["active", "display_name", "notes"]
    back = client.patch(f"{URL}/{p['id']}", json={"active": True}, headers=admin_headers)
    assert back.json()["data"]["partner"]["active"] is True
    assert len(_audit("partner.update")) == 2


def test_patch_noop_writes_no_audit_row(client, admin_headers):
    p = _create(client, admin_headers, "Acme", display_name="X")
    for body in ({}, {"display_name": "X", "active": True, "internal_name": "  Acme "}):
        response = client.patch(f"{URL}/{p['id']}", json=body, headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["data"]["partner"]["display_name"] == "X"
    assert _audit("partner.update") == []


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ({"internal_name": None}, "internal_name: cannot be null"),
        ({"active": None}, "active: cannot be null"),
        ({"active": "yes"}, "active"),
        ({"internal_name": "x"}, "internal_name: must be 2 to 160 characters"),
        ({"notes": "n" * 5001}, "notes: must be at most 5000"),
    ],
)
def test_patch_validation_errors(client, admin_headers, body, fragment):
    p = _create(client, admin_headers, "Acme")
    response = client.patch(f"{URL}/{p['id']}", json=body, headers=admin_headers)
    assert response.status_code == 422
    assert fragment in response.json()["detail"]["message"]
    assert _audit("partner.update") == []


@pytest.mark.parametrize("pid", ["999999", "0", "abc", "99999999999"])
def test_patch_unknown_id_is_404(client, admin_headers, pid):
    response = client.patch(f"{URL}/{pid}", json={"active": False}, headers=admin_headers)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"


def test_rename_collision_is_409_and_changes_nothing(client, admin_headers):
    _create(client, admin_headers, "Acme")
    other = _create(client, admin_headers, "Globex")
    response = client.patch(
        f"{URL}/{other['id']}", json={"internal_name": "  ACME ", "notes": "x"}, headers=admin_headers
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "partner_exists"
    row = _rows("SELECT internal_name, notes FROM partner WHERE id = :i", i=other["id"])[0]
    assert row["internal_name"] == "Globex" and row["notes"] is None
    assert _audit("partner.update") == []


def test_case_only_rename_is_allowed(client, admin_headers):
    p = _create(client, admin_headers, "acme payments")
    response = client.patch(f"{URL}/{p['id']}", json={"internal_name": "Acme Payments"}, headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["data"]["partner"]["internal_name"] == "Acme Payments"
    assert _audit("partner.update")[0]["detail"]["changed_fields"] == ["internal_name"]


def test_rename_rewrites_mirror_on_the_partners_listings_only(
    client, admin_headers, create_opportunity
):
    acme = _create(client, admin_headers, "Acme Payments Pvt Ltd")
    globex = _create(client, admin_headers, "Globex")
    a1 = create_opportunity()
    a2 = create_opportunity(status="closed")
    other = create_opportunity()
    _attach(a1["id"], acme["id"], "Acme Payments Pvt Ltd")
    _attach(a2["id"], acme["id"], "Acme Payments Pvt Ltd")
    _attach(other["id"], globex["id"], "Globex")
    before = _rows("SELECT id, updated_at FROM opportunity ORDER BY id")
    response = client.patch(
        f"{URL}/{acme['id']}", json={"internal_name": "Acme Payments Limited"}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["partner"]["opportunity_count"] == 2
    mirror = {
        r["id"]: r["partner_internal_name"]
        for r in _rows("SELECT id, partner_internal_name FROM opportunity")
    }
    assert mirror[a1["id"]] == mirror[a2["id"]] == "Acme Payments Limited"
    assert mirror[other["id"]] == "Globex"
    assert _rows("SELECT id, updated_at FROM opportunity ORDER BY id") == before


def test_display_name_change_does_not_touch_listing_public_name(
    client, admin_headers, create_opportunity
):
    partner = _create(client, admin_headers, "Acme")
    opp = create_opportunity(partner_display_name="Public Name")
    _attach(opp["id"], partner["id"], "Acme")
    client.patch(f"{URL}/{partner['id']}", json={"display_name": "Different"}, headers=admin_headers)
    assert _rows(
        "SELECT partner_display_name FROM opportunity WHERE id = :i", i=opp["id"]
    )[0]["partner_display_name"] == "Public Name"


# --------------------------------------------------------------------------- resolve_partner


def _resolve(**kw):
    from src.workshop0.db.session import create_db_session
    from src.workshop0.services.partners import resolve_partner

    args = dict(
        partner_id=None, partner_id_given=False, internal_name=None, internal_name_given=False,
        display_name_hint=None, current_partner_id=None, by="admin-key",
    )
    args.update(kw)
    with create_db_session() as session:
        try:
            partner = resolve_partner(session, **args)
            return None if partner is None else partner.id
        except Exception as exc:  # noqa: BLE001 - surface HTTPException detail
            detail = getattr(exc, "detail", None)
            return detail["message"] if isinstance(detail, dict) else exc


def test_resolve_by_id_unknown_inactive_and_current(client, admin_headers):
    p = _create(client, admin_headers, "Acme")
    assert _resolve(partner_id=p["id"], partner_id_given=True) == p["id"]
    assert _resolve(partner_id=424242, partner_id_given=True) == "partner_id: partner 424242 does not exist"
    assert _resolve(partner_id=None, partner_id_given=True, current_partner_id=p["id"]) is None
    client.patch(f"{URL}/{p['id']}", json={"active": False}, headers=admin_headers)
    assert _resolve(partner_id=p["id"], partner_id_given=True) == "partner_id: partner is inactive"
    assert _resolve(partner_id=p["id"], partner_id_given=True, current_partner_id=p["id"]) == p["id"]


def test_resolve_by_name_matches_creates_with_audit_and_clears(client, admin_headers):
    p = _create(client, admin_headers, "Acme Payments")
    assert _resolve(internal_name=" ACME  payments", internal_name_given=True) == p["id"]
    assert _resolve(internal_name=None, internal_name_given=True, current_partner_id=p["id"]) is None
    assert _resolve(internal_name="  ", internal_name_given=True) is None
    assert _resolve(current_partner_id=p["id"]) == p["id"]  # neither given: kept
    assert _resolve() is None
    assert _rows("SELECT count(*) AS n FROM partner")[0]["n"] == 1

    from src.workshop0.db.session import create_db_session
    from src.workshop0.services.partners import resolve_partner

    with create_db_session() as session:
        created = resolve_partner(
            session, partner_id=None, partner_id_given=False, internal_name="New  Org",
            internal_name_given=True, display_name_hint="A new org", current_partner_id=None,
            by="boss@example.test",
        )
        session.commit()
        new_id = created.id
    row = _rows("SELECT internal_name, display_name, active FROM partner WHERE id = :i", i=new_id)[0]
    assert (row["internal_name"], row["display_name"], row["active"]) == ("New Org", "A new org", True)
    (audit,) = [a for a in _audit("partner.create") if a["subject_id"] == new_id]
    assert audit["detail"] == {"internal_name": "New Org", "by": "boss@example.test"}


def test_resolve_by_name_inactive_rule_and_bad_name(client, admin_headers):
    p = _create(client, admin_headers, "Acme")
    client.patch(f"{URL}/{p['id']}", json={"active": False}, headers=admin_headers)
    assert _resolve(internal_name="acme", internal_name_given=True) == "partner_id: partner is inactive"
    assert _resolve(internal_name="acme", internal_name_given=True, current_partner_id=p["id"]) == p["id"]
    assert "partner_internal_name" in _resolve(internal_name="x", internal_name_given=True)
    assert _rows("SELECT count(*) AS n FROM partner")[0]["n"] == 1


def test_resolve_both_given_agree_or_conflict(client, admin_headers):
    a = _create(client, admin_headers, "Acme")
    b = _create(client, admin_headers, "Globex")
    both = dict(partner_id_given=True, internal_name_given=True)
    assert _resolve(partner_id=a["id"], internal_name="acme", **both) == a["id"]
    assert _resolve(partner_id=None, internal_name=None, **both) is None
    conflict = "partner_id: conflicts with partner_internal_name"
    assert _resolve(partner_id=a["id"], internal_name="Globex", **both) == conflict
    assert _resolve(partner_id=a["id"], internal_name="Unknown Org", **both) == conflict
    assert _resolve(partner_id=a["id"], internal_name=None, **both) == conflict
    assert _resolve(partner_id=None, internal_name="Globex", **both) == conflict
    assert _resolve(partner_id=None, internal_name="Unknown Org", **both) == conflict
    assert _rows("SELECT count(*) AS n FROM partner")[0]["n"] == 2  # a conflict never creates
    assert b["id"]


def test_partner_ref_and_active_partners_never_leak_notes(client, admin_headers):
    from src.workshop0.db.session import create_db_session
    from src.workshop0.services.partners import active_partners, partner_ref

    keep = _create(client, admin_headers, "Beta", notes="secret terms", display_name="A firm")
    off = _create(client, admin_headers, "Alpha")
    client.patch(f"{URL}/{off['id']}", json={"active": False}, headers=admin_headers)
    with create_db_session() as session:
        listed = active_partners(session)
        assert [p.id for p in listed] == [keep["id"]]
        ref = partner_ref(listed[0])
    assert ref == {"id": keep["id"], "internal_name": "Beta", "display_name": "A firm", "active": True}


def test_log_events_carry_ids_only(monkeypatch, make_app, admin_headers):
    import src.workshop0.config.settings as settings_module
    from fastapi.testclient import TestClient
    from structlog.testing import capture_logs

    monkeypatch.setenv("WORKSHOP0_LOG_LEVEL", "INFO")
    settings_module._settings = None
    client = TestClient(make_app())
    with capture_logs() as events:
        p = _create(client, admin_headers, "Very Secret Org Name", notes="private-notes-token")
        client.patch(f"{URL}/{p['id']}", json={"notes": "another-private-token"}, headers=admin_headers)
    by_event = {e["event"]: e for e in events if e["event"].startswith("partner.")}
    assert by_event["partner.created"]["partner_id"] == p["id"]
    assert by_event["partner.updated"]["partner_id"] == p["id"]
    blob = json.dumps(list(by_event.values()), default=str)
    assert "Very Secret Org Name" not in blob and "private-notes-token" not in blob
    assert "another-private-token" not in blob
