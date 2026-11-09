"""Admin invites, Phase 11d (spec/api.md §Phase 11d): revoke, create re-use/refresh,
`invite_already_accepted`, and the derived `revoked` / `superseded` statuses."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text

from src.workshop0.db.models import FacilitatorAction, NetworkInvite
from src.workshop0.db.session import create_db_session
from tests.conftest import NETWORK_HEADERS

BASE = "/api/admin/network/invites"


def audits(action: str) -> list[FacilitatorAction]:
    with create_db_session() as session:
        return list(
            session.scalars(
                select(FacilitatorAction)
                .where(FacilitatorAction.action == action)
                .order_by(FacilitatorAction.id)
            )
        )


def invite_count() -> int:
    with create_db_session() as session:
        return int(session.scalar(select(func.count()).select_from(NetworkInvite)) or 0)


def row(invite_id: int) -> NetworkInvite:
    with create_db_session() as session:
        return session.get(NetworkInvite, invite_id)


def accept(invite_id: int, user_id: int | None = None) -> None:
    with create_db_session() as session:
        session.execute(
            text("UPDATE network_invite SET accepted_at = :t, accepted_user_id = :u WHERE id = :id"),
            {"t": datetime.now(timezone.utc), "u": user_id, "id": invite_id},
        )


def create(client, headers, email: str, name: str | None = None):
    body = {"email": email} if name is None else {"email": email, "name": name}
    return client.post(BASE, json=body, headers=headers)


def parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- revoke


def test_revoke_pending_invite_then_repeat_is_idempotent(client, admin_headers):
    created = create(client, admin_headers, "r@example.test").json()["data"]
    assert created["reused"] is False
    inv = created["invite"]
    assert inv["revoked_at"] is None and inv["revoked_by"] is None

    response = client.post(f"{BASE}/{inv['id']}/revoke", headers=admin_headers)
    assert response.status_code == 200, response.text
    payload = response.json()["data"]["invite"]
    assert payload["status"] == "revoked"
    assert payload["revoked_by"] == "admin-key"  # AdminActor.by, same as created_by
    assert payload["revoked_at"] is not None
    stored = row(inv["id"])
    assert stored.revoked_at is not None and stored.revoked_by == payload["revoked_by"]
    revokes = audits("invite.revoke")
    assert len(revokes) == 1
    assert revokes[0].actor == "admin" and revokes[0].subject_type == "invite"
    assert revokes[0].subject_id == inv["id"]
    assert json.loads(revokes[0].detail_json) == {"email": "r@example.test", "by": payload["revoked_by"]}

    again = client.post(f"{BASE}/{inv['id']}/revoke", headers=admin_headers)
    assert again.status_code == 200
    assert again.json()["data"]["invite"] == payload
    assert len(audits("invite.revoke")) == 1

    listed = client.get(BASE, headers=admin_headers).json()["data"]["invites"]
    assert [i["status"] for i in listed] == ["revoked"]


def test_revoke_expired_invite_is_allowed(client, admin_headers):
    inv = create(client, admin_headers, "old@example.test").json()["data"]["invite"]
    with create_db_session() as session:
        session.execute(
            text("UPDATE network_invite SET expires_at = :e WHERE id = :id"),
            {"e": datetime.now(timezone.utc) - timedelta(seconds=1), "id": inv["id"]},
        )
    response = client.post(f"{BASE}/{inv['id']}/revoke", headers=admin_headers)
    assert response.status_code == 200 and response.json()["data"]["invite"]["status"] == "revoked"


def test_revoke_accepted_invite_is_409(client, admin_headers):
    inv = create(client, admin_headers, "acc@example.test").json()["data"]["invite"]
    accept(inv["id"])
    response = client.post(f"{BASE}/{inv['id']}/revoke", headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "invite_not_revocable",
        "message": "An accepted invite can't be revoked.",
    }
    assert row(inv["id"]).revoked_at is None
    assert audits("invite.revoke") == []


def test_revoke_unknown_or_bad_id_is_404(client, admin_headers):
    for path in (f"{BASE}/999999/revoke", f"{BASE}/abc/revoke", f"{BASE}/0/revoke"):
        response = client.post(path, headers=admin_headers)
        assert response.status_code == 404, path
        assert response.json()["detail"]["code"] == "not_found"


def test_revoke_without_a_key_is_401(client, admin_headers):
    inv = create(client, admin_headers, "k@example.test").json()["data"]["invite"]
    response = client.post(f"{BASE}/{inv['id']}/revoke")
    assert response.status_code == 401
    assert row(inv["id"]).revoked_at is None


def test_revoke_by_cookie_admin_needs_the_csrf_header(client, admin_headers, make_user, signed_in_client):
    inv = create(client, admin_headers, "c@example.test").json()["data"]["invite"]
    admin = make_user("boss@example.test", admin=True)
    no_csrf = signed_in_client(admin, csrf=False).post(f"{BASE}/{inv['id']}/revoke")
    assert no_csrf.status_code == 403
    assert no_csrf.json()["detail"]["code"] == "csrf_failed"
    assert row(inv["id"]).revoked_at is None

    ok = signed_in_client(admin).post(f"{BASE}/{inv['id']}/revoke", headers=NETWORK_HEADERS)
    assert ok.status_code == 200
    assert ok.json()["data"]["invite"]["revoked_by"] == "boss@example.test"


# --------------------------------------------------------------------------- create re-use


def test_creating_a_pending_email_twice_reuses_and_refreshes(client, admin_headers):
    first = create(client, admin_headers, "dup@example.test", name="Ravi").json()["data"]
    with create_db_session() as session:  # age the invite so the renewal is observable
        session.execute(
            text("UPDATE network_invite SET expires_at = :e WHERE id = :id"),
            {"e": datetime.now(timezone.utc) + timedelta(days=2), "id": first["invite"]["id"]},
        )
    token_before = row(first["invite"]["id"]).token

    response = create(client, admin_headers, " DUP@example.test ", name="Ravi K")
    assert response.status_code == 200
    second = response.json()["data"]
    assert second["reused"] is True
    assert second["invite"]["id"] == first["invite"]["id"]
    assert second["invite"]["url"] == first["invite"]["url"]
    assert second["invite"]["name"] == "Ravi K"
    assert second["invite"]["status"] == "pending"
    renewed = parse(second["invite"]["expires_at"])
    assert abs((renewed - datetime.now(timezone.utc)) - timedelta(days=14)) < timedelta(minutes=1)
    assert row(first["invite"]["id"]).token == token_before
    assert invite_count() == 1
    refreshes = audits("invite.refresh")
    assert len(refreshes) == 1 and refreshes[0].subject_id == first["invite"]["id"]
    assert json.loads(refreshes[0].detail_json)["email"] == "dup@example.test"
    assert len(audits("invite.create")) == 1

    # an empty name keeps the existing one
    third = create(client, admin_headers, "dup@example.test", name="  ").json()["data"]
    assert third["reused"] is True and third["invite"]["name"] == "Ravi K"


def test_creating_for_an_accepted_email_is_409_and_writes_nothing(client, admin_headers):
    inv = create(client, admin_headers, "joined@example.test").json()["data"]["invite"]
    accept(inv["id"])
    response = create(client, admin_headers, "Joined@example.test")
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "invite_already_accepted",
        "message": "This email has already joined through an invite.",
    }
    assert invite_count() == 1
    assert audits("invite.refresh") == [] and len(audits("invite.create")) == 1


def test_after_revoke_or_expiry_a_new_row_is_created(client, admin_headers):
    first = create(client, admin_headers, "again@example.test").json()["data"]["invite"]
    client.post(f"{BASE}/{first['id']}/revoke", headers=admin_headers)
    second = create(client, admin_headers, "again@example.test").json()["data"]
    assert second["reused"] is False and second["invite"]["id"] != first["id"]
    assert second["invite"]["url"] != first["url"]

    with create_db_session() as session:
        session.execute(
            text("UPDATE network_invite SET expires_at = :e WHERE id = :id"),
            {"e": datetime.now(timezone.utc) - timedelta(seconds=1), "id": second["invite"]["id"]},
        )
    third = create(client, admin_headers, "again@example.test").json()["data"]
    assert third["reused"] is False and invite_count() == 3


# --------------------------------------------------------------------------- statuses


def test_sibling_of_an_accepted_invite_lists_as_superseded(client, admin_headers):
    a = create(client, admin_headers, "sib@example.test").json()["data"]["invite"]
    client.post(f"{BASE}/{a['id']}/revoke", headers=admin_headers)
    b = create(client, admin_headers, "sib@example.test").json()["data"]["invite"]
    c = create(client, admin_headers, "other@example.test").json()["data"]["invite"]
    # a legacy duplicate pending row (pre-11d data) for the same email
    with create_db_session() as session:
        legacy = NetworkInvite(
            token="legacy-token-11d",
            email="sib@example.test",
            created_by="admin key",
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
            expires_at=datetime.now(timezone.utc) + timedelta(days=13),
        )
        session.add(legacy)
        session.flush()
        legacy_id = legacy.id
    accept(b["id"])
    listed = client.get(BASE, headers=admin_headers).json()["data"]["invites"]
    statuses = {i["id"]: i["status"] for i in listed}
    assert statuses == {a["id"]: "revoked", b["id"]: "accepted", c["id"]: "pending", legacy_id: "superseded"}

    # superseded is revocable
    response = client.post(f"{BASE}/{legacy_id}/revoke", headers=admin_headers)
    assert response.status_code == 200 and response.json()["data"]["invite"]["status"] == "revoked"
