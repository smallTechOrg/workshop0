"""C19 workshop tie-in: admin facilitator links, audit, validation, trainer view (PostgreSQL)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select

from src.workshop0.db.models import (
    AppUser,
    FacilitatorAction,
    TrainerProfile,
    Workshop,
    WorkshopFacilitator,
)
from src.workshop0.db.session import create_db_session
from src.workshop0.services import tiein


def _profile(name: str = "Asha Rao") -> int:
    with create_db_session() as s:
        user = AppUser(
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            email_verified=True,
            display_name=name,
            oidc_issuer="https://accounts.google.com",
            oidc_subject=uuid.uuid4().hex,
        )
        s.add(user)
        s.flush()
        p = TrainerProfile(
            user_id=user.id,
            headline=f"{name} headline",
            consent_at=datetime.now(timezone.utc),
            consent_version="v1",
        )
        s.add(p)
        s.flush()
        return p.id


def _audit(workshop_id: int) -> list[dict]:
    with create_db_session() as s:
        rows = s.scalars(
            select(FacilitatorAction)
            .where(FacilitatorAction.action == "workshop.facilitators")
            .where(FacilitatorAction.workshop_id == workshop_id)
            .order_by(FacilitatorAction.id)
        ).all()
        return [
            {"actor": r.actor, "detail": json.loads(r.detail_json), "subject": (r.subject_type, r.subject_id)}
            for r in rows
        ]


def _url(workshop) -> str:
    return f"/api/admin/workshops/{workshop['id']}/facilitators"


def _put(client, headers, workshop, items):
    return client.put(_url(workshop), json={"facilitators": items}, headers=headers)


def _err(response, status, code="validation_error") -> str:
    assert response.status_code == status, response.text
    detail = response.json()["detail"]
    assert detail["code"] == code
    return detail["message"]


def test_empty_get_then_put_orders_and_exposes_admin_fields(client, admin_headers, workshop):
    assert client.get(_url(workshop), headers=admin_headers).json()["data"] == {"facilitators": []}
    a, b, c = _profile("Asha"), _profile("Bala"), _profile("Chitra")
    r = _put(client, admin_headers, workshop, [
        {"profile_id": c, "role": "ta"}, {"profile_id": b, "role": "co"}, {"profile_id": a, "role": "lead"},
    ])
    assert r.status_code == 200, r.text
    rows = r.json()["data"]["facilitators"]
    assert [(x["profile_id"], x["role"]) for x in rows] == [(a, "lead"), (b, "co"), (c, "ta")]
    first = rows[0]
    assert set(first) == {"profile_id", "role", "display_name", "headline", "email", "linked_by", "created_at"}
    assert first["display_name"] == "Asha" and first["linked_by"] == "admin-key"
    assert first["email"].endswith("@example.com") and first["created_at"].endswith("Z")
    # persisted: GET agrees
    assert client.get(_url(workshop), headers=admin_headers).json()["data"]["facilitators"] == rows
    audit = _audit(workshop["id"])
    assert len(audit) == 1 and audit[0]["actor"] == "admin" and audit[0]["subject"] == ("workshop", workshop["id"])
    assert sorted(x["profile_id"] for x in audit[0]["detail"]["added"]) == sorted([a, b, c])
    assert audit[0]["detail"]["removed"] == [] and audit[0]["detail"]["by"] == "admin-key"
    # audit detail carries ids and roles only
    assert "email" not in json.dumps(audit[0]["detail"])


def test_identical_put_is_noop_without_audit(client, admin_headers, workshop):
    a = _profile()
    _put(client, admin_headers, workshop, [{"profile_id": a, "role": "co"}])
    r = _put(client, admin_headers, workshop, [{"profile_id": a, "role": "co"}])
    assert r.status_code == 200 and len(_audit(workshop["id"])) == 1
    # empty set on an empty workshop is also a no-op
    other = client.post("/api/admin/workshops", json={"name": "Other", "description_md": "x", "milestones": [
        {"title": "m", "content_md": "c", "minutes": 5}]}, headers=admin_headers).json()["data"]["workshop"]
    assert _put(client, admin_headers, other, []).status_code == 200
    assert _audit(other["id"]) == []


def test_replace_reports_added_removed_changed(client, admin_headers, workshop):
    a, b, c = _profile(), _profile(), _profile()
    _put(client, admin_headers, workshop, [{"profile_id": a, "role": "lead"}, {"profile_id": b, "role": "co"}])
    r = _put(client, admin_headers, workshop, [{"profile_id": b, "role": "lead"}, {"profile_id": c, "role": "ta"}])
    assert r.status_code == 200, r.text
    assert [(x["profile_id"], x["role"]) for x in r.json()["data"]["facilitators"]] == [(b, "lead"), (c, "ta")]
    d = _audit(workshop["id"])[1]["detail"]
    assert d["added"] == [{"profile_id": c, "role": "ta"}]
    assert d["removed"] == [a]
    assert d["changed"] == [{"profile_id": b, "role": "lead"}]
    # clearing removes all
    assert _put(client, admin_headers, workshop, []).json()["data"]["facilitators"] == []


def test_lead_swap_in_one_put(client, admin_headers, workshop):
    a, b = _profile(), _profile()
    _put(client, admin_headers, workshop, [{"profile_id": a, "role": "lead"}, {"profile_id": b, "role": "co"}])
    r = _put(client, admin_headers, workshop, [{"profile_id": a, "role": "co"}, {"profile_id": b, "role": "lead"}])
    assert r.status_code == 200, r.text
    assert [(x["profile_id"], x["role"]) for x in r.json()["data"]["facilitators"]] == [(b, "lead"), (a, "co")]


@pytest.mark.parametrize("make,needle", [
    (lambda a, b: [{"profile_id": a, "role": "lead"}, {"profile_id": b, "role": "lead"}], "facilitators[1]"),
    (lambda a, b: [{"profile_id": a, "role": "co"}, {"profile_id": a, "role": "ta"}], "facilitators[1]"),
    (lambda a, b: [{"profile_id": a, "role": "boss"}], "facilitators[0]"),
    (lambda a, b: [{"profile_id": a}], "facilitators[0]"),
    (lambda a, b: [{"profile_id": "7", "role": "co"}], "facilitators[0]"),
    (lambda a, b: [{"profile_id": True, "role": "co"}], "facilitators[0]"),
    (lambda a, b: [{"profile_id": a, "role": "co"}, {"profile_id": 99999999, "role": "co"}], "facilitators[1]"),
    (lambda a, b: ["nope"], "facilitators[0]"),
])
def test_put_validation_names_entry_and_writes_nothing(client, admin_headers, workshop, make, needle):
    a, b = _profile(), _profile()
    message = _err(_put(client, admin_headers, workshop, make(a, b)), 422)
    assert needle in message
    assert client.get(_url(workshop), headers=admin_headers).json()["data"]["facilitators"] == []
    assert _audit(workshop["id"]) == []


def test_put_limit_ten_and_not_a_list(client, admin_headers, workshop):
    ids = [_profile() for _ in range(11)]
    ten = [{"profile_id": i, "role": "co"} for i in ids[:10]]
    assert _put(client, admin_headers, workshop, ten).status_code == 200
    _err(_put(client, admin_headers, workshop, ten + [{"profile_id": ids[10], "role": "co"}]), 422)
    _err(client.put(_url(workshop), json={}, headers=admin_headers), 422)
    _err(client.put(_url(workshop), json={"facilitators": "x"}, headers=admin_headers), 422)


def test_post_adds_updates_and_audits(client, admin_headers, workshop):
    a, b = _profile(), _profile()
    r = client.post(_url(workshop), json={"profile_id": a, "role": "co"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert [(x["profile_id"], x["role"]) for x in r.json()["data"]["facilitators"]] == [(a, "co")]
    # default role is co
    r = client.post(_url(workshop), json={"profile_id": b}, headers=admin_headers)
    assert {(x["profile_id"], x["role"]) for x in r.json()["data"]["facilitators"]} == {(a, "co"), (b, "co")}
    # update to lead
    r = client.post(_url(workshop), json={"profile_id": a, "role": "lead"}, headers=admin_headers)
    assert r.json()["data"]["facilitators"][0]["profile_id"] == a
    audit = _audit(workshop["id"])
    assert len(audit) == 3 and audit[2]["detail"]["changed"] == [{"profile_id": a, "role": "lead"}]
    # same again is a no-op
    client.post(_url(workshop), json={"profile_id": a, "role": "lead"}, headers=admin_headers)
    assert len(_audit(workshop["id"])) == 3


def test_post_validation(client, admin_headers, workshop):
    a, b = _profile(), _profile()
    client.post(_url(workshop), json={"profile_id": a, "role": "lead"}, headers=admin_headers)
    _err(client.post(_url(workshop), json={"profile_id": b, "role": "lead"}, headers=admin_headers), 422)
    _err(client.post(_url(workshop), json={"profile_id": 99999999, "role": "co"}, headers=admin_headers), 422)
    _err(client.post(_url(workshop), json={"profile_id": b, "role": "x"}, headers=admin_headers), 422)
    _err(client.post(_url(workshop), json={"role": "co"}, headers=admin_headers), 422)
    assert len(_audit(workshop["id"])) == 1


def test_post_beyond_ten_rejected(client, admin_headers, workshop):
    for _ in range(10):
        assert client.post(_url(workshop), json={"profile_id": _profile()}, headers=admin_headers).status_code == 200
    _err(client.post(_url(workshop), json={"profile_id": _profile()}, headers=admin_headers), 422)


def test_unknown_workshop_is_404_everywhere(client, admin_headers):
    path = "/api/admin/workshops/99999999/facilitators"
    a = _profile()
    _err(client.get(path, headers=admin_headers), 404, "not_found")
    _err(client.put(path, json={"facilitators": []}, headers=admin_headers), 404, "not_found")
    _err(client.post(path, json={"profile_id": a}, headers=admin_headers), 404, "not_found")


def test_requires_admin(client, workshop):
    path = _url(workshop)
    assert client.get(path).status_code in (401, 403)
    assert client.put(path, json={"facilitators": []}).status_code in (401, 403)
    assert client.post(path, json={"profile_id": 1}).status_code in (401, 403)
    assert client.get(path, headers={"X-Admin-Key": "wrong"}).status_code in (401, 403)


def test_workshops_for_is_own_view_without_leaks(client, admin_headers, workshop):
    a, b = _profile("Asha"), _profile("Bala")
    _put(client, admin_headers, workshop, [{"profile_id": a, "role": "lead"}, {"profile_id": b, "role": "co"}])
    with create_db_session() as s:
        token = s.get(Workshop, workshop["id"]).admin_token
        mine = tiein.workshops_for(s, a, base_url="http://testserver/")
        none = tiein.workshops_for(s, 99999999, base_url="http://testserver")
    assert none == []
    assert len(mine) == 1
    row = mine[0]
    assert set(row) == {"workshop_id", "name", "status", "role", "facilitator_url", "linked_at"}
    assert row["role"] == "lead" and row["workshop_id"] == workshop["id"]
    assert row["facilitator_url"] == f"http://testserver/f/{token}"
    blob = json.dumps(mine)
    assert "example.com" not in blob and "Bala" not in blob


def test_workshops_for_newest_link_first_and_unlink_hides_without_rotating_token(client, admin_headers, workshop):
    other = client.post("/api/admin/workshops", json={"name": "Second", "description_md": "x", "milestones": [
        {"title": "m", "content_md": "c", "minutes": 5}]}, headers=admin_headers).json()["data"]["workshop"]
    a = _profile()
    _put(client, admin_headers, workshop, [{"profile_id": a, "role": "co"}])
    _put(client, admin_headers, other, [{"profile_id": a, "role": "ta"}])
    with create_db_session() as s:
        token = s.get(Workshop, workshop["id"]).admin_token
        names = [w["name"] for w in tiein.workshops_for(s, a, base_url="http://x")]
    assert names == ["Second", workshop["name"]]
    _put(client, admin_headers, workshop, [])
    with create_db_session() as s:
        assert [w["workshop_id"] for w in tiein.workshops_for(s, a, base_url="http://x")] == [other["id"]]
        assert s.get(Workshop, workshop["id"]).admin_token == token  # not rotated


def test_cascades_on_profile_and_workshop_delete(client, admin_headers, workshop):
    a, b = _profile(), _profile()
    _put(client, admin_headers, workshop, [{"profile_id": a, "role": "co"}, {"profile_id": b, "role": "ta"}])
    with create_db_session() as s:
        s.execute(delete(TrainerProfile).where(TrainerProfile.id == a))
    rows = client.get(_url(workshop), headers=admin_headers).json()["data"]["facilitators"]
    assert [x["profile_id"] for x in rows] == [b]
    with create_db_session() as s:
        s.execute(delete(Workshop).where(Workshop.id == workshop["id"]))
    with create_db_session() as s:
        assert s.scalars(select(WorkshopFacilitator)).all() == []
