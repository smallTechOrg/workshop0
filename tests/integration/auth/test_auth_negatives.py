"""Every refused sign-in: 303 → `/app/signin/?error=<code>`, no user row, no session row,
no session cookie (spec/roadmap.md §Phase 11 Gate conditions → OIDC)."""

from __future__ import annotations

import pytest
from auth_helpers import cookie_header, count, query_of, reload_settings, sign_in, start
from itsdangerous import URLSafeTimedSerializer
from tests.support.fake_oidc import authorize_redirect

from src.workshop0.db.models import AppUser, AuthSession

SESSION_COOKIE = "workshop0_session"


def assert_refused(response, code: str) -> None:
    assert response.status_code == 303, response.text
    location = response.headers["location"]
    assert location.startswith("/app/signin/?")
    assert query_of(location) == {"error": code, "next": "/app/network/"}
    assert cookie_header(response, SESSION_COOKIE) is None
    assert count(AuthSession) == 0
    assert count(AppUser) == 0


@pytest.mark.parametrize(
    ("email", "code"),
    [
        ("unverified+n1@example.test", "email_unverified"),
        ("wrongaud+n2@example.test", "idp_error"),  # aud != client id
        ("n3+expired@example.test", "idp_error"),  # exp an hour ago, beyond the 60 s leeway
        ("badsig+n4@example.test", "idp_error"),  # signed by a second key, published kid
        ("unknownkid+n5@example.test", "idp_error"),  # second key, unknown kid (refetch, then refuse)
        ("wrongiss+n6@example.test", "idp_error"),
        ("badnonce+n7@example.test", "idp_error"),  # nonce mismatch
    ],
)
def test_bad_id_tokens_are_refused_with_the_documented_code(client, email, code):
    result = sign_in(client, email)
    assert_refused(result.response, code)
    assert client.get("/api/auth/me").json()["data"]["user"] is None


def test_state_mismatch_is_refused(client):
    started = start(client)
    callback = authorize_redirect(started.headers["location"], "state1@example.test")
    q = query_of(callback)
    tampered = callback.replace(f"state={q['state']}", "state=not-the-state-we-sent")
    assert_refused(client.get(tampered, follow_redirects=False), "state_mismatch")


def test_callback_without_the_state_cookie_is_refused(client, make_client):
    started = start(client)
    callback = authorize_redirect(started.headers["location"], "state2@example.test")
    other_browser = make_client()  # e.g. a login-CSRF attempt: no workshop0_oidc cookie
    assert_refused(other_browser.get(callback, follow_redirects=False), "state_mismatch")


def test_state_cookie_with_a_forged_signature_is_refused(client):
    started = start(client)
    callback = authorize_redirect(started.headers["location"], "state3@example.test")
    q = query_of(callback)
    forged = URLSafeTimedSerializer("attacker-secret", salt="workshop0.oidc-state.v1").dumps(
        {"s": q["state"], "n": "x", "v": "y" * 64, "next": "/app/network/", "invite": None}
    )
    client.cookies.clear()  # drop the genuine cookie; plant only the forged one
    client.cookies.set("workshop0_oidc", forged, path="/api/auth/google")
    assert_refused(client.get(callback, follow_redirects=False), "state_mismatch")


def test_state_cookie_older_than_ten_minutes_is_refused(client, monkeypatch):
    import time

    from itsdangerous.timed import TimestampSigner

    original = TimestampSigner.get_timestamp
    monkeypatch.setattr(TimestampSigner, "get_timestamp", lambda self: int(time.time()) - 601)
    started = start(client)  # cookie timestamped 10 min + 1 s ago
    monkeypatch.setattr(TimestampSigner, "get_timestamp", original)
    callback = authorize_redirect(started.headers["location"], "state4@example.test")
    assert_refused(client.get(callback, follow_redirects=False), "state_mismatch")


def test_state_cookie_from_another_server_secret_is_refused(client, monkeypatch):
    started = start(client)
    callback = authorize_redirect(started.headers["location"], "state5@example.test")
    monkeypatch.setenv("WORKSHOP0_SESSION_SECRET", "rotated-" + "0" * 56)
    reload_settings()
    assert_refused(client.get(callback, follow_redirects=False), "state_mismatch")


def test_idp_cancel_is_refused_as_idp_error(client):
    started = start(client)
    state = query_of(started.headers["location"])["state"]
    response = client.get(
        f"/api/auth/google/callback?error=access_denied&state={state}", follow_redirects=False
    )
    assert_refused(response, "idp_error")


def test_replayed_authorization_code_is_refused(client):
    first = sign_in(client, "replay@example.test")
    assert first.response.status_code == 303
    # The state cookie was cleared at the callback, so a replay cannot even reach the IdP.
    replay = client.get(first.callback_url, follow_redirects=False)
    assert replay.status_code == 303
    assert query_of(replay.headers["location"]) == {"error": "state_mismatch", "next": "/app/network/"}
    assert count(AuthSession) == 1


def test_unreachable_issuer_redirects_with_idp_error(client, monkeypatch):
    monkeypatch.setenv("WORKSHOP0_OIDC_ISSUER", "http://127.0.0.1:9")
    reload_settings()
    response = start(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/app/signin/?error=idp_error&next=%2Fapp%2Fnetwork%2F"


def test_failed_callback_keeps_next_for_the_retry(client):
    result = sign_in(client, "unverified+n8@example.test", next="/app/network/me/")
    assert result.response.status_code == 303
    location = result.response.headers["location"]
    assert location.startswith("/app/signin/?")
    assert query_of(location) == {"error": "email_unverified", "next": "/app/network/me/"}
    assert count(AuthSession) == 0
