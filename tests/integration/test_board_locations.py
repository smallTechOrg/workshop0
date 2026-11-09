"""Phase 11c multi-location listings through the real admin + public API (PostgreSQL).

Contract: spec/api.md §Phase 11c; invariants + read rule: spec/data-model.md §Phase 11c."""

import json

import pytest
from sqlalchemy import text

from tests.conftest import db_execute, opportunity_body

THREE = [{"city": "Bengaluru", "country": "India"}, {"city": "Pune"}, {"city": "Hyderabad"}]
THREE_OUT = [
    {"city": "Bengaluru", "country": "India"},
    {"city": "Pune", "country": None},
    {"city": "Hyderabad", "country": None},
]
SHAPE = "locations: each location needs a city and an optional country"


def _db_row(opportunity_id: int) -> dict:
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        row = session.execute(
            text("SELECT city, locations_json, location_mode, updated_at FROM opportunity WHERE id = :id"),
            {"id": opportunity_id},
        ).one()
        return {**row._mapping, "locations": json.loads(row.locations_json)}


def _count(table: str) -> int:
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        return int(session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())


def _audit_since(before_id: int) -> list[dict]:
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        rows = session.execute(
            text("SELECT action, detail_json FROM facilitator_action WHERE id > :id ORDER BY id"),
            {"id": before_id},
        ).all()
    return [{"action": r.action, "detail": json.loads(r.detail_json)} for r in rows]


def _max_audit_id() -> int:
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        return int(session.execute(text("SELECT coalesce(max(id), 0) FROM facilitator_action")).scalar_one())


@pytest.fixture
def post(client, admin_headers, topic_ids):
    def _post(**overrides):
        body = opportunity_body([topic_ids["python"]], **overrides)
        return client.post("/api/admin/opportunities", json=body, headers=admin_headers)

    return _post


@pytest.fixture
def patch(client, admin_headers):
    def _patch(opportunity_id: int, body: dict):
        return client.patch(f"/api/admin/opportunities/{opportunity_id}", json=body, headers=admin_headers)

    return _patch


def _ok(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()["data"]["opportunity"]


def _error(response) -> str:
    assert response.status_code == 422, response.text
    return response.json()["detail"]["message"]


# --------------------------------------------------------------------------- round trip


def test_round_trip_admin_public_and_city_mirror(client, admin_headers, post):
    opp = _ok(post(status="open", location_mode="hybrid", locations=THREE))
    assert opp["locations"] == THREE_OUT and opp["city"] == "Bengaluru"

    admin = client.get(f"/api/admin/opportunities/{opp['id']}", headers=admin_headers)
    assert admin.json()["data"]["opportunity"]["locations"] == THREE_OUT
    rows = client.get("/api/admin/opportunities", headers=admin_headers).json()["data"]["opportunities"]
    assert [r["locations"] for r in rows if r["id"] == opp["id"]] == [THREE_OUT]

    public = client.get(f"/api/public/opportunities/{opp['id']}")
    assert public.status_code == 200
    detail = public.json()["data"]["opportunity"]
    assert detail["locations"] == THREE_OUT and detail["city"] == "Bengaluru"
    assert "locations_json" not in public.text
    cards = client.get("/api/public/opportunities").json()["data"]["opportunities"]
    card = next(c for c in cards if c["id"] == opp["id"])
    assert card["locations"] == THREE_OUT and card["city"] == "Bengaluru"

    db = _db_row(opp["id"])
    assert db["city"] == "Bengaluru" and db["locations"] == THREE_OUT


def test_normalization_and_dedupe(post):
    opp = _ok(post(location_mode="onsite", locations=[
        {"city": " pune "}, {"city": "PUNE"}, {"city": "Pune", "country": "India"},
        {"city": "  New   Delhi ", "country": " "},
    ]))
    assert opp["locations"] == [
        {"city": "pune", "country": None},
        {"city": "Pune", "country": "India"},
        {"city": "New Delhi", "country": None},
    ]
    assert _db_row(opp["id"])["city"] == "pune"


# --------------------------------------------------------------------------- bounds


def test_ten_locations_accepted_and_eleven_with_a_duplicate_stores_ten(post):
    ten = [{"city": f"City {i}"} for i in range(10)]
    assert len(_ok(post(location_mode="onsite", locations=ten))["locations"]) == 10
    opp = _ok(post(location_mode="onsite", locations=ten + [{"city": "CITY 3"}]))
    assert len(opp["locations"]) == 10 and len(_db_row(opp["id"])["locations"]) == 10


@pytest.mark.parametrize(
    ("locations", "message"),
    [
        ([{"city": f"City {i}"} for i in range(11)], "locations: at most 10 locations"),
        ([{"city": "c" * 81}], "locations: city must be 1–80 characters"),
        ([{"city": "   "}], "locations: city must be 1–80 characters"),
        ([{"city": "Pune", "country": "c" * 81}], "locations: country must be at most 80 characters"),
        ([{"city": "Pune", "state": "MH"}], SHAPE),
        ("Pune", SHAPE),
        ([{"country": "India"}], SHAPE),
    ],
)
def test_bounds_reject_and_write_nothing(post, locations, message):
    before = (_count("opportunity"), _count("facilitator_action"))
    assert _error(post(location_mode="onsite", locations=locations)) == message
    assert (_count("opportunity"), _count("facilitator_action")) == before


def test_patch_rejection_writes_nothing(post, patch):
    opp = _ok(post(location_mode="hybrid", locations=THREE))
    assert _error(patch(opp["id"], {"locations": [{"city": "x" * 81}]})) == (
        "locations: city must be 1–80 characters"
    )
    assert _db_row(opp["id"])["locations"] == THREE_OUT


# --------------------------------------------------------------------------- mode rules


def test_onsite_with_empty_locations_uses_the_locations_message(post):
    assert _error(post(location_mode="onsite", locations=[])) == (
        "locations: add at least one city for onsite or hybrid"
    )
    assert _error(post(location_mode="hybrid", locations=None)) == (
        "locations: add at least one city for onsite or hybrid"
    )


def test_onsite_with_neither_field_uses_the_phase10_city_message(post):
    assert _error(post(location_mode="onsite")) == "city: required for onsite or hybrid"


def test_remote_forces_empty_list_and_null_city(post):
    opp = _ok(post(location_mode="remote", locations=THREE[:2]))
    assert opp["locations"] == [] and opp["city"] is None
    db = _db_row(opp["id"])
    assert db["locations"] == [] and db["city"] is None


def test_patch_mode_transitions(post, patch):
    opp = _ok(post(location_mode="hybrid", locations=THREE))
    remote = _ok(patch(opp["id"], {"location_mode": "remote"}))
    assert remote["locations"] == [] and remote["city"] is None
    assert _db_row(opp["id"])["city"] is None
    assert _error(patch(opp["id"], {"location_mode": "onsite"})) == "city: required for onsite or hybrid"
    assert _db_row(opp["id"])["location_mode"] == "remote"


# --------------------------------------------------------------------------- legacy city


def test_legacy_city_post_becomes_one_location(post):
    opp = _ok(post(location_mode="onsite", city="  Navi   Mumbai "))
    assert opp["locations"] == [{"city": "Navi Mumbai", "country": None}]
    assert opp["city"] == "Navi Mumbai" and _db_row(opp["id"])["city"] == "Navi Mumbai"


def test_legacy_city_patch_replaces_the_whole_list(post, patch):
    opp = _ok(post(location_mode="hybrid", locations=THREE))
    before = _max_audit_id()
    updated = _ok(patch(opp["id"], {"city": "Mumbai"}))
    assert updated["locations"] == [{"city": "Mumbai", "country": None}]
    assert updated["city"] == "Mumbai" and _db_row(opp["id"])["city"] == "Mumbai"
    rows = _audit_since(before)
    assert [r["action"] for r in rows] == ["opportunity.update"]
    assert rows[0]["detail"]["changed_fields"] == ["locations"]


def test_locations_win_when_both_fields_are_sent(post, patch):
    opp = _ok(post(location_mode="onsite", city="Chennai", locations=THREE))
    assert opp["locations"] == THREE_OUT and opp["city"] == "Bengaluru"
    updated = _ok(patch(opp["id"], {"city": "Ignored", "locations": [{"city": "Delhi"}]}))
    assert updated["locations"] == [{"city": "Delhi", "country": None}]


# --------------------------------------------------------------------------- audit


def test_reorder_is_one_update_reporting_locations(post, patch):
    opp = _ok(post(location_mode="hybrid", locations=THREE))
    before = _max_audit_id()
    reordered = [THREE[2], THREE[0], THREE[1]]
    updated = _ok(patch(opp["id"], {"locations": reordered}))
    assert [l["city"] for l in updated["locations"]] == ["Hyderabad", "Bengaluru", "Pune"]
    assert updated["city"] == "Hyderabad" and _db_row(opp["id"])["city"] == "Hyderabad"
    rows = _audit_since(before)
    assert len(rows) == 1 and rows[0]["action"] == "opportunity.update"
    assert rows[0]["detail"]["changed_fields"] == ["locations"]


def test_same_list_or_equal_legacy_city_is_a_no_op(post, patch):
    opp = _ok(post(location_mode="hybrid", locations=THREE))
    before = _max_audit_id()
    same = _ok(patch(opp["id"], {"locations": [{"city": " bengaluru ", "country": "INDIA"}, *THREE[1:]]}))
    # case-only edits are normalized-equal under the key but the stored text differs → a change
    assert same["locations"][0]["city"] == "bengaluru"
    before = _max_audit_id()
    again = _ok(patch(opp["id"], {"locations": same["locations"]}))
    assert again["updated_at"] == same["updated_at"] and _audit_since(before) == []

    single = _ok(post(location_mode="onsite", locations=[{"city": "Pune"}]))
    before = _max_audit_id()
    legacy = _ok(patch(single["id"], {"city": " Pune "}))
    assert legacy["updated_at"] == single["updated_at"] and _audit_since(before) == []


# --------------------------------------------------------------------------- read rule


def test_read_rule_falls_back_to_city_for_a_0007_written_row(client, create_opportunity):
    opp = create_opportunity(status="open")
    db_execute(
        "UPDATE opportunity SET locations_json = '[]', city = 'Pune', location_mode = 'onsite' WHERE id = :id",
        id=opp["id"],
    )
    card = client.get(f"/api/public/opportunities/{opp['id']}").json()["data"]["opportunity"]
    assert card["locations"] == [{"city": "Pune", "country": None}] and card["city"] == "Pune"


def test_admin_q_does_not_match_cities(client, admin_headers, post):
    _ok(post(location_mode="hybrid", locations=[{"city": "Zzqcity"}]))
    data = client.get("/api/admin/opportunities", params={"q": "zzqcity"}, headers=admin_headers).json()
    assert data["data"]["total"] == 0
