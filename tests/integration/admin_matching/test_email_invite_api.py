"""POST /api/admin/network/invites/{id}/email (spec/api.md §Phase 12; 11d invite states)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from src.workshop0.db.models import EmailOutbox, FacilitatorAction, NetworkInvite
from src.workshop0.db.session import create_db_session

INVITES = "/api/admin/network/invites"


def _create(client, headers, email="new.trainer@example.test") -> int:
    r = client.post(INVITES, json={"email": email, "name": "New Trainer"}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["invite"]["id"]


def _counts() -> tuple[int, int]:
    with create_db_session() as session:
        return (
            session.scalar(select(func.count()).select_from(EmailOutbox)),
            session.scalar(select(func.count()).select_from(FacilitatorAction).where(FacilitatorAction.action == "invite.email")),
        )


def test_requires_admin_and_unknown_invite_is_404(client, admin_headers):
    invite_id = _create(client, admin_headers)
    assert client.post(f"{INVITES}/{invite_id}/email").status_code == 401
    assert client.post(f"{INVITES}/999999/email", headers=admin_headers).status_code == 404


def test_create_does_not_auto_email(client, admin_headers):
    _create(client, admin_headers)
    assert _counts() == (0, 0)


def test_pending_invite_enqueues_one_row_and_one_audit_second_click_adds_nothing(client, admin_headers):
    invite_id = _create(client, admin_headers)
    first = client.post(f"{INVITES}/{invite_id}/email", headers=admin_headers)
    assert first.status_code == 200, first.text
    outbox = first.json()["data"]["outbox"]
    assert outbox["status"] in {"queued", "recorded", "sent"}
    assert _counts() == (1, 1)
    second = client.post(f"{INVITES}/{invite_id}/email", headers=admin_headers)
    assert second.status_code == 200 and second.json()["data"]["outbox"]["id"] == outbox["id"]
    assert _counts() == (1, 1)
    with create_db_session() as session:
        audit = session.scalar(select(FacilitatorAction).where(FacilitatorAction.action == "invite.email"))
        detail = json.loads(audit.detail_json)
        assert audit.subject_type == "invite" and audit.subject_id == invite_id
        assert "new.trainer@example.test" not in audit.detail_json and detail["to"].endswith("@example.test")
        row = session.get(EmailOutbox, outbox["id"])
        assert row.template == "network.invite" and row.to_email == "new.trainer@example.test"


def test_revoked_used_and_expired_invites_are_refused_with_409_and_nothing_written(client, admin_headers):
    revoked = _create(client, admin_headers, "a@example.test")
    assert client.post(f"{INVITES}/{revoked}/revoke", headers=admin_headers).status_code == 200
    used = _create(client, admin_headers, "b@example.test")
    expired = _create(client, admin_headers, "c@example.test")
    with create_db_session() as session:
        session.get(NetworkInvite, used).accepted_at = datetime.now(timezone.utc)
        session.get(NetworkInvite, expired).expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    for invite_id, code in ((revoked, "invite_revoked"), (used, "invite_used"), (expired, "invite_expired")):
        r = client.post(f"{INVITES}/{invite_id}/email", headers=admin_headers)
        assert r.status_code == 409 and r.json()["detail"]["code"] == code
    assert _counts() == (0, 0)
