"""Invite acceptance at the callback (spec/api.md §Phase 11 → Invite acceptance).

Accepting = signing in with the SAME email. Mismatch/expired are checked before any user or
session write; a failure creates no user, no session and changes no invite. An existing
profile is verified at the callback (the one profile write outside `/api/me`)."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone

from auth_helpers import count, query_of, rows, sign_in
from sqlalchemy import select

from src.workshop0.db.models import (
    AppUser,
    AuthSession,
    FacilitatorAction,
    NetworkInvite,
    TrainerProfile,
)
from src.workshop0.db.session import create_db_session


def make_invite(email: str, *, expires_in: timedelta = timedelta(days=14)) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with create_db_session() as session:
        session.add(
            NetworkInvite(
                token=token,
                email=email.lower(),
                name="Invited Trainer",
                created_by="admin@example.test",
                created_at=now,
                expires_at=now + expires_in,
            )
        )
    return token


def invite_row(token: str) -> NetworkInvite:
    return next(i for i in rows(NetworkInvite) if i.token == token)


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


def profile_of(user_id: int) -> TrainerProfile:
    with create_db_session() as session:
        return session.scalar(select(TrainerProfile).where(TrainerProfile.user_id == user_id))


def me(client) -> dict:
    return client.get("/api/auth/me").json()["data"]["user"]


def test_matching_email_accepts_the_invite_and_me_reports_invite_accepted(client):
    token = make_invite("invitee@example.test")
    result = sign_in(client, "Invitee@Example.test", next="/app/network/join/", invite=token)
    assert result.response.status_code == 303
    assert result.location == "/app/network/join/"

    user = rows(AppUser)[0]
    invite = invite_row(token)
    assert invite.accepted_at is not None
    assert invite.accepted_user_id == user.id
    assert count(AuthSession) == 1
    body = me(client)
    assert body["invite_accepted"] is True
    assert body["has_profile"] is False


def test_matching_email_verifies_an_existing_profile_and_audits_it(client, make_user):
    user = make_user("hasprofile@example.test")
    profile_id = add_profile(user.id)
    token = make_invite("hasprofile@example.test")

    assert sign_in(client, "hasprofile@example.test", invite=token).response.status_code == 303
    profile = profile_of(user.id)
    assert profile.verified is True
    assert profile.verified_at is not None
    assert profile.verified_by == "admin@example.test"  # network_invite.created_by
    assert profile.headline == "GenAI trainer"  # no other column touched
    audits = [a for a in rows(FacilitatorAction) if a.action == "trainer.verify"]
    assert len(audits) == 1
    assert audits[0].actor == "user"
    assert audits[0].subject_type == "trainer" and audits[0].subject_id == profile_id
    assert json.loads(audits[0].detail_json) == {"via": "invite", "invite_id": invite_row(token).id}
    assert me(client)["invite_accepted"] is True


def test_already_verified_profile_is_left_alone(client, make_user):
    user = make_user("verified@example.test")
    add_profile(user.id, verified=True)
    token = make_invite("verified@example.test")
    assert sign_in(client, "verified@example.test", invite=token).response.status_code == 303
    assert profile_of(user.id).verified_by == "someone@example.test"
    assert not [a for a in rows(FacilitatorAction) if a.action == "trainer.verify"]
    assert invite_row(token).accepted_user_id == user.id


def test_different_email_is_refused_with_the_masked_invite_email_and_nothing_is_written(client):
    token = make_invite("invitee@example.test")
    result = sign_in(client, "someone-else@example.test", next="/app/network/join/", invite=token)
    assert result.response.status_code == 303
    location = result.response.headers["location"]
    assert location.startswith("/app/signin/?error=invite_email_mismatch&")
    assert query_of(location) == {
        "error": "invite_email_mismatch",
        "invite": token,
        "invite_email": "in***@example.test",
        "next": "/app/network/join/",
    }
    assert "invitee@example.test" not in location
    assert count(AppUser) == 0
    assert count(AuthSession) == 0
    invite = invite_row(token)
    assert invite.accepted_at is None and invite.accepted_user_id is None
    assert me(client) is None


def test_mismatch_for_an_existing_account_changes_nothing(client, make_user):
    user = make_user("existing@example.test")
    add_profile(user.id)
    token = make_invite("invitee@example.test")
    result = sign_in(client, "existing@example.test", invite=token)
    assert query_of(result.response.headers["location"])["error"] == "invite_email_mismatch"
    assert count(AuthSession) == 0
    assert profile_of(user.id).verified is False
    assert invite_row(token).accepted_at is None


def test_expired_invite_is_refused_without_the_invite_param(client):
    token = make_invite("late@example.test", expires_in=timedelta(seconds=-1))
    result = sign_in(client, "late@example.test", next="/app/network/join/", invite=token)
    assert query_of(result.response.headers["location"]) == {
        "error": "invite_expired",
        "next": "/app/network/join/",
    }
    assert count(AppUser) == 0
    assert count(AuthSession) == 0
    assert invite_row(token).accepted_at is None


def test_unknown_invite_token_is_a_normal_sign_in(client):
    result = sign_in(client, "ghost@example.test", invite="no-such-invite-token")
    assert result.response.status_code == 303
    assert result.location == "/app/network/"
    assert count(AuthSession) == 1
    assert me(client)["invite_accepted"] is False


def test_reusing_an_accepted_invite_as_the_same_user_is_a_no_op_success(client, make_client):
    token = make_invite("again@example.test")
    assert sign_in(client, "again@example.test", invite=token).response.status_code == 303
    accepted_at = invite_row(token).accepted_at

    second_browser = make_client()
    second = sign_in(second_browser, "again@example.test", invite=token)
    assert second.response.status_code == 303
    assert second.location == "/app/network/"
    assert invite_row(token).accepted_at == accepted_at  # not re-stamped
    assert count(AuthSession) == 2
    assert me(second_browser)["invite_accepted"] is True


def test_invite_accepted_by_a_deleted_account_grants_nothing_to_a_new_one(client, make_client):
    token = make_invite("reuse@example.test")
    assert sign_in(client, "reuse@example.test", invite=token).response.status_code == 303
    with create_db_session() as session:
        session.query(AppUser).delete()  # account deletion: accepted_user_id → NULL

    fresh = make_client()
    result = sign_in(fresh, "reuse@example.test", invite=token)
    assert result.response.status_code == 303
    assert result.location == "/app/network/"
    assert me(fresh)["invite_accepted"] is False
    assert invite_row(token).accepted_user_id is None


def test_invite_query_param_alone_never_grants_invite_accepted(client):
    make_invite("noinvite@example.test")
    assert sign_in(client, "noinvite@example.test", next="/app/network/join/").response.status_code == 303
    assert me(client)["invite_accepted"] is False


def test_malformed_invite_parameter_is_ignored(client):
    result = sign_in(client, "plain@example.test", invite="<script>")
    assert result.response.status_code == 303
    assert result.location == "/app/network/"
    assert count(AuthSession) == 1
