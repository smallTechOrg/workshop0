"""C11 sign-in happy paths through the real OIDC round-trip (spec/api.md §Phase 11 → Auth)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from auth_helpers import (
    CLIENT_ID,
    cookie_header,
    count,
    query_of,
    rows,
    sign_in,
    start,
)
from fastapi.testclient import TestClient

from src.workshop0.db.models import AppUser, AuthSession

SESSION_COOKIE = "workshop0_session"
OIDC_COOKIE = "workshop0_oidc"


def test_start_redirects_to_the_issuer_with_pkce_state_nonce_and_a_signed_state_cookie(
    client, fake_issuer
):
    response = start(client, next="/app/network/me/")
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(f"{fake_issuer.base_url}/authorize?")
    q = query_of(location)
    assert q["response_type"] == "code"
    assert q["client_id"] == CLIENT_ID
    assert q["redirect_uri"] == "http://testserver/api/auth/google/callback"
    assert q["scope"] == "openid email profile"
    assert q["code_challenge_method"] == "S256"
    assert len(q["code_challenge"]) == 43  # base64url(SHA-256) without padding
    assert q["prompt"] == "select_account"
    assert len(q["state"]) >= 32 and len(q["nonce"]) >= 32 and q["state"] != q["nonce"]

    header = cookie_header(response, OIDC_COOKIE)
    assert header is not None
    lowered = header.lower()
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    assert "max-age=600" in lowered
    assert "secure" not in lowered  # http base URL
    assert "path=/api/auth/google" in lowered


def test_first_sign_in_creates_one_user_and_one_session_and_sets_the_session_cookie(client):
    result = sign_in(client, "Trainer.One@Example.test")
    assert result.response.status_code == 303
    assert result.location == "/app/network/"

    header = cookie_header(result.response, SESSION_COOKIE)
    assert header is not None
    lowered = header.lower()
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    assert "path=/" in lowered
    assert f"max-age={30 * 24 * 3600}" in lowered
    assert "secure" not in lowered
    cleared = cookie_header(result.response, OIDC_COOKIE)
    assert cleared is not None and "max-age=0" in cleared.lower()

    users = rows(AppUser)
    assert len(users) == 1
    user = users[0]
    assert user.email == "trainer.one@example.test"  # lower-cased
    assert user.email_verified is True
    assert user.oidc_issuer and user.oidc_subject
    assert user.display_name  # name claim (fallback: email local part)
    assert user.last_login_at is not None
    sessions_ = rows(AuthSession)
    assert len(sessions_) == 1
    assert sessions_[0].user_id == user.id
    raw_token = header.split(";", 1)[0].split("=", 1)[1]
    assert sessions_[0].token_hash != raw_token and len(sessions_[0].token_hash) == 64

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["user"] == {
        "id": user.id,
        "email": "trainer.one@example.test",
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "is_admin": False,
        "has_profile": False,
        "invite_accepted": False,
    }


def test_second_sign_in_reuses_the_same_user(client, make_client):
    first = sign_in(client, "repeat@example.test")
    assert first.response.status_code == 303
    first_user = rows(AppUser)[0]

    other_browser = make_client()
    second = sign_in(other_browser, "repeat@example.test")
    assert second.response.status_code == 303

    users = rows(AppUser)
    assert len(users) == 1
    assert users[0].id == first_user.id
    assert users[0].last_login_at >= first_user.last_login_at
    assert count(AuthSession) == 2
    assert other_browser.get("/api/auth/me").json()["data"]["user"]["id"] == first_user.id


def test_sign_in_lands_on_a_guarded_next_path(client):
    result = sign_in(client, "nexter@example.test", next="/app/network/me/?tab=cv")
    assert result.response.status_code == 303
    assert result.location == "/app/network/me/?tab=cv"


@pytest.mark.parametrize(
    "evil",
    [
        "https://evil.example",
        "https://evil.example/app/network/",
        "//evil.example/app/",
        "/\\evil.example",
        "/app\\..\\evil",
        "/admin/",
        "javascript:alert(1)",
        "/app/ x",
        "",
    ],
)
def test_open_redirect_guard_lands_on_the_network_home(client, evil):
    result = sign_in(client, f"guard-{abs(hash(evil))}@example.test", next=evil)
    assert result.response.status_code == 303
    assert result.location == "/app/network/"


def test_sign_in_claims_an_invite_created_placeholder_row_with_the_same_email(client):
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        placeholder = AppUser(
            email="placeholder@example.test",
            email_verified=False,
            display_name="placeholder",
            oidc_issuer=None,
            oidc_subject=None,
            created_at=datetime.now(timezone.utc),
        )
        session.add(placeholder)
        session.flush()
        placeholder_id = placeholder.id

    result = sign_in(client, "placeholder@example.test")
    assert result.response.status_code == 303
    users = rows(AppUser)
    assert [u.id for u in users] == [placeholder_id]
    assert users[0].oidc_issuer is not None and users[0].oidc_subject is not None
    assert users[0].email_verified is True


def test_session_cookie_is_secure_when_the_base_url_is_https(app):
    secure_client = TestClient(app, base_url="https://testserver")
    started = start(secure_client)
    assert started.status_code == 302
    assert "secure" in cookie_header(started, OIDC_COOKIE).lower()
    assert query_of(started.headers["location"])["redirect_uri"] == (
        "https://testserver/api/auth/google/callback"
    )
    result = sign_in(secure_client, "secure@example.test")
    assert result.response.status_code == 303, result.location
    assert "secure" in cookie_header(result.response, SESSION_COOKIE).lower()


def test_start_is_rate_limited_to_20_per_minute_per_ip(client, monkeypatch):
    from src.workshop0.services import ratelimit

    frozen = datetime(2026, 11, 9, 10, 0, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(ratelimit, "_utcnow", lambda: frozen)
    for _ in range(20):
        assert start(client).status_code == 302
    blocked = start(client)
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "rate_limited"
    assert int(blocked.headers["retry-after"]) == 55
