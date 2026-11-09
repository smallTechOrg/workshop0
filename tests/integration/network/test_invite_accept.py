"""`POST /api/me/invite/accept` — apply an invite to the signed-in user without a second
Google round-trip (spec/api.md §Phase 11d; same checks as the callback, §Invite acceptance)."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from src.workshop0.db.models import AuthSession, FacilitatorAction, NetworkInvite, TrainerProfile
from src.workshop0.db.session import create_db_session

URL = "/api/me/invite/accept"


def make_invite(
    email: str,
    *,
    expires_in: timedelta = timedelta(days=14),
    revoked: bool = False,
    accepted_by: int | None = None,
    accepted: bool = False,
) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with create_db_session() as session:
        session.add(
            NetworkInvite(
                token=token,
                email=email,
                created_by="admin@example.test",
                created_at=now,
                expires_at=now + expires_in,
                revoked_at=now if revoked else None,
                revoked_by="admin key" if revoked else None,
                accepted_at=now if (accepted or accepted_by) else None,
                accepted_user_id=accepted_by,
            )
        )
    return token


def invite(token: str) -> NetworkInvite:
    with create_db_session() as session:
        return session.scalar(select(NetworkInvite).where(NetworkInvite.token == token))


def add_profile(user_id: int, *, verified: bool = False) -> int:
    with create_db_session() as session:
        profile = TrainerProfile(
            user_id=user_id,
            headline="GenAI trainer",
            consent_at=datetime.now(timezone.utc),
            consent_version="2026-11",
            verified=verified,
            verified_by="someone@example.test" if verified else None,
        )
        session.add(profile)
        session.flush()
        return profile.id


def profile(user_id: int) -> TrainerProfile:
    with create_db_session() as session:
        return session.scalar(select(TrainerProfile).where(TrainerProfile.user_id == user_id))


def verify_audits() -> list[FacilitatorAction]:
    with create_db_session() as session:
        return list(
            session.scalars(select(FacilitatorAction).where(FacilitatorAction.action == "trainer.verify"))
        )


def session_count() -> int:
    with create_db_session() as session:
        return int(session.scalar(select(func.count()).select_from(AuthSession)) or 0)


def error_of(response) -> dict:
    return response.json()["detail"]


# --------------------------------------------------------------------------- happy path


def test_accept_verifies_an_existing_unverified_profile_and_audits_once(make_user, signed_in_client):
    user = make_user("trainer@example.test")
    profile_id = add_profile(user.id)
    token = make_invite("trainer@example.test")
    client = signed_in_client(user)
    sessions_before = session_count()

    response = client.post(URL, json={"token": token})
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"invite_accepted": True, "profile_verified": True}

    row = invite(token)
    assert row.accepted_at is not None and row.accepted_user_id == user.id
    p = profile(user.id)
    assert p.verified is True and p.verified_by == "admin@example.test" and p.verified_at is not None
    audits = verify_audits()
    assert len(audits) == 1 and audits[0].actor == "user" and audits[0].subject_id == profile_id
    assert json.loads(audits[0].detail_json) == {"via": "invite", "invite_id": row.id}
    assert session_count() == sessions_before  # never creates a session
    assert client.get("/api/auth/me").json()["data"]["user"]["invite_accepted"] is True

    # second call: no-op success, no new writes
    again = client.post(URL, json={"token": token})
    assert again.status_code == 200
    assert again.json()["data"] == {"invite_accepted": True, "profile_verified": False}
    assert len(verify_audits()) == 1
    assert invite(token).accepted_at == row.accepted_at


def test_accept_without_a_profile_stamps_the_invite_only(make_user, signed_in_client):
    user = make_user("noprofile@example.test")
    token = make_invite("noprofile@example.test")
    response = signed_in_client(user).post(URL, json={"token": token})
    assert response.json()["data"] == {"invite_accepted": True, "profile_verified": False}
    assert invite(token).accepted_user_id == user.id
    assert verify_audits() == []


def test_superseded_invite_for_the_siblings_acceptor_is_a_no_op(make_user, signed_in_client):
    user = make_user("sib@example.test")
    make_invite("sib@example.test", accepted_by=user.id)
    second = make_invite("sib@example.test")
    response = signed_in_client(user).post(URL, json={"token": second})
    assert response.status_code == 200
    assert response.json()["data"] == {"invite_accepted": True, "profile_verified": False}
    assert invite(second).accepted_at is None


# --------------------------------------------------------------------------- auth guards


def test_without_a_session_is_401(client):
    token = make_invite("x@example.test")
    response = client.post(URL, json={"token": token}, headers={"X-Requested-With": "workshop0"})
    assert response.status_code == 401
    assert error_of(response)["code"] == "not_signed_in"
    assert invite(token).accepted_at is None


def test_without_the_csrf_header_is_403(make_user, signed_in_client):
    user = make_user("csrf@example.test")
    token = make_invite("csrf@example.test")
    response = signed_in_client(user, csrf=False).post(URL, json={"token": token})
    assert response.status_code == 403
    assert error_of(response)["code"] == "csrf_failed"
    assert invite(token).accepted_at is None


# --------------------------------------------------------------------------- error codes


def test_unknown_missing_or_malformed_token_is_404(make_user, signed_in_client):
    client = signed_in_client(make_user("ghost@example.test"))
    for body in ({"token": "no-such-token"}, {}, {"token": "<script>"}, {"token": 42}):
        response = client.post(URL, json=body)
        assert response.status_code == 404, body
        assert error_of(response)["code"] == "invite_not_found"


def test_revoked_is_410(make_user, signed_in_client):
    user = make_user("rev@example.test")
    add_profile(user.id)
    token = make_invite("rev@example.test", revoked=True)
    response = signed_in_client(user).post(URL, json={"token": token})
    assert response.status_code == 410
    assert error_of(response) == {
        "code": "invite_revoked",
        "message": "This invite has been withdrawn — ask smallTech for a new one.",
    }
    assert invite(token).accepted_at is None and profile(user.id).verified is False


def test_used_by_someone_else_is_409_even_with_a_different_email(make_user, signed_in_client):
    owner = make_user("owner@example.test")
    token = make_invite("owner@example.test", accepted_by=owner.id)
    for email in ("owner-b@example.test", "other@example.test"):
        response = signed_in_client(make_user(email)).post(URL, json={"token": token})
        assert response.status_code == 409
        assert error_of(response) == {"code": "invite_used", "message": "This invite has already been used."}
    assert invite(token).accepted_user_id == owner.id


def test_used_by_a_deleted_account_is_409(make_user, signed_in_client):
    token = make_invite("gone@example.test", accepted=True)  # accepted_user_id NULL
    response = signed_in_client(make_user("gone@example.test")).post(URL, json={"token": token})
    assert response.status_code == 409 and error_of(response)["code"] == "invite_used"


def test_expired_is_410(make_user, signed_in_client):
    user = make_user("late@example.test")
    token = make_invite("late@example.test", expires_in=timedelta(seconds=-1))
    response = signed_in_client(user).post(URL, json={"token": token})
    assert response.status_code == 410 and error_of(response)["code"] == "invite_expired"
    assert invite(token).accepted_at is None


def test_email_mismatch_is_409_with_the_masked_invite_email(make_user, signed_in_client):
    user = make_user("me@example.test")
    add_profile(user.id)
    token = make_invite("invitee@example.test")
    response = signed_in_client(user).post(URL, json={"token": token})
    assert response.status_code == 409
    detail = error_of(response)
    assert detail["code"] == "invite_email_mismatch"
    assert detail["details"] == {"invite_email": "in***@example.test"}
    assert "invitee@example.test" not in response.text
    assert invite(token).accepted_at is None and profile(user.id).verified is False


def test_rate_limited_after_20_per_hour(make_user, signed_in_client):
    client = signed_in_client(make_user("busy@example.test"))
    for _ in range(20):
        assert client.post(URL, json={"token": "nope"}).status_code == 404
    blocked = client.post(URL, json={"token": "nope"})
    assert blocked.status_code == 429
    assert error_of(blocked)["code"] == "rate_limited"
    assert blocked.headers.get("retry-after")
