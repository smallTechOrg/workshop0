"""`/api/auth/config`, `/api/auth/me`, `/api/auth/signout`, and the startup rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from auth_helpers import cookie_header, reload_settings, rows, sign_in, start

from src.workshop0.db.models import AuthSession, TrainerProfile
from tests.conftest import create_session_token

CSRF = {"X-Requested-With": "workshop0"}


def test_config_reports_google_enabled(client):
    response = client.get("/api/auth/config")
    assert response.status_code == 200
    assert response.json()["data"] == {"google_enabled": True}


@pytest.mark.parametrize("blank", ["WORKSHOP0_GOOGLE_CLIENT_ID", "WORKSHOP0_GOOGLE_CLIENT_SECRET"])
def test_sign_in_disabled_without_client_credentials(make_app, monkeypatch, blank):
    from fastapi.testclient import TestClient

    monkeypatch.setenv(blank, "")
    monkeypatch.setenv("WORKSHOP0_SESSION_SECRET", "")  # not required when disabled
    reload_settings()
    client = TestClient(make_app())
    assert client.get("/api/auth/config").json()["data"] == {"google_enabled": False}
    response = start(client)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "signin_not_configured"
    callback = client.get("/api/auth/google/callback?code=x&state=y", follow_redirects=False)
    assert callback.status_code == 303
    assert callback.headers["location"] == (
        "/app/signin/?error=signin_not_configured&next=%2Fapp%2Fnetwork%2F"
    )
    assert client.get("/api/auth/me").json()["data"] == {"user": None}


def test_me_is_null_when_signed_out_never_401(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == {"data": {"user": None}, "error": None}
    client.cookies.set("workshop0_session", "not-a-real-token")
    assert client.get("/api/auth/me").json()["data"]["user"] is None


def test_me_is_null_for_an_expired_session(client, make_user):
    user = make_user("expired-session@example.test")
    token = create_session_token(user.id, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    client.cookies.set("workshop0_session", token)
    assert client.get("/api/auth/me").json()["data"]["user"] is None


def test_me_reports_has_profile(client, make_user, signed_in_client):
    from src.workshop0.db.session import create_db_session

    user = make_user("profiled@example.test")
    trainer = signed_in_client(user)
    assert trainer.get("/api/auth/me").json()["data"]["user"]["has_profile"] is False
    with create_db_session() as session:
        session.add(
            TrainerProfile(
                user_id=user.id,
                headline="GenAI trainer",
                consent_at=datetime.now(timezone.utc),
                consent_version="2026-11",
            )
        )
    body = trainer.get("/api/auth/me").json()["data"]["user"]
    assert body["has_profile"] is True
    assert body["email"] == "profiled@example.test"


def test_signout_revokes_the_session_and_clears_the_cookie(client):
    assert sign_in(client, "leaver@example.test").response.status_code == 303
    assert client.get("/api/auth/me").json()["data"]["user"] is not None

    response = client.post("/api/auth/signout", headers=CSRF)
    assert response.status_code == 200
    assert response.json()["data"] == {"signed_out": True}
    cleared = cookie_header(response, "workshop0_session")
    assert cleared is not None and "max-age=0" in cleared.lower()
    sessions_ = rows(AuthSession)
    assert len(sessions_) == 1 and sessions_[0].revoked_at is not None

    assert client.get("/api/auth/me").json()["data"]["user"] is None
    again = client.post("/api/auth/signout", headers=CSRF)  # idempotent
    assert again.status_code == 200


def test_revoked_session_token_no_longer_authenticates(client, make_client):
    assert sign_in(client, "stolen@example.test").response.status_code == 303
    token = client.cookies.get("workshop0_session")
    assert client.post("/api/auth/signout", headers=CSRF).status_code == 200
    replay = make_client()
    replay.cookies.set("workshop0_session", token)
    assert replay.get("/api/auth/me").json()["data"]["user"] is None


def test_signout_without_the_csrf_header_is_refused(client):
    assert sign_in(client, "csrf@example.test").response.status_code == 303
    response = client.post("/api/auth/signout")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "csrf_failed"
    assert client.get("/api/auth/me").json()["data"]["user"] is not None


# --------------------------------------------------------------------------- startup rules


def _settings(**overrides):
    from src.workshop0.config.settings import Settings

    base = {
        "workshop0_google_client_id": "id",
        "workshop0_google_client_secret": "secret",
        "workshop0_oidc_issuer": "https://accounts.google.com",
        "workshop0_session_secret": "s" * 64,
    }
    base.update(overrides)
    return Settings(**base)


@pytest.mark.parametrize(
    "issuer", ["https://accounts.google.com", "http://localhost:8099", "http://127.0.0.1:8099/"]
)
def test_startup_accepts_https_and_local_http_issuers(issuer):
    from src.workshop0.auth.startup import validate_settings

    validate_settings(_settings(workshop0_oidc_issuer=issuer))


@pytest.mark.parametrize(
    "issuer", ["http://issuer.example", "http://localhost.evil.example", "ftp://localhost", "accounts.google.com"]
)
def test_startup_refuses_a_non_local_http_or_malformed_issuer(issuer):
    from src.workshop0.auth.startup import validate_settings

    with pytest.raises(RuntimeError, match="WORKSHOP0_OIDC_ISSUER"):
        validate_settings(_settings(workshop0_oidc_issuer=issuer))


def test_startup_requires_the_session_secret_only_when_sign_in_is_enabled(make_app, monkeypatch):
    from src.workshop0.auth.startup import validate_settings

    with pytest.raises(RuntimeError, match="WORKSHOP0_SESSION_SECRET"):
        validate_settings(_settings(workshop0_session_secret=""))
    validate_settings(_settings(workshop0_session_secret="", workshop0_google_client_id=""))

    monkeypatch.setenv("WORKSHOP0_SESSION_SECRET", "")
    reload_settings()
    with pytest.raises(RuntimeError, match="WORKSHOP0_SESSION_SECRET"):
        make_app()
