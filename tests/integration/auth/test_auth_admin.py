"""Admin via session in `require_admin_key` (spec/architecture.md §Network identity).

Allowlisted email → admin endpoints without the key; de-listed → 403 `not_admin` on the
next request; the key path is byte-for-byte unchanged; an empty `X-Admin-Key: ""` header
(the existing frontend always sends it) counts as absent."""

from __future__ import annotations

import pytest
from auth_helpers import ADMIN_EMAIL, reload_settings, sign_in

from tests.conftest import TEST_ADMIN_KEY, WORKSHOP_BODY

CSRF = {"X-Requested-With": "workshop0"}
KEY_FAILURE = {
    "code": "invalid_admin_key",
    "message": "The access key is missing or does not match this server's WORKSHOP0_ADMIN_KEY.",
}


@pytest.fixture
def admin_client(client):
    result = sign_in(client, ADMIN_EMAIL)
    assert result.response.status_code == 303 and result.location == "/app/network/"
    return client


def test_allowlisted_admin_reaches_admin_endpoints_without_the_key(admin_client):
    me = admin_client.get("/api/auth/me").json()["data"]["user"]
    assert me["is_admin"] is True

    listed = admin_client.get("/api/admin/workshops")
    assert listed.status_code == 200, listed.text
    with_empty_key = admin_client.get("/api/admin/workshops", headers={"X-Admin-Key": ""})
    assert with_empty_key.status_code == 200, with_empty_key.text
    assert admin_client.get("/api/admin/network/trainers").status_code == 200

    created = admin_client.post(
        "/api/admin/workshops", json=WORKSHOP_BODY, headers={**CSRF, "X-Admin-Key": ""}
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["workshop"]["name"] == WORKSHOP_BODY["name"]
    names = [w["name"] for w in admin_client.get("/api/admin/workshops").json()["data"]["workshops"]]
    assert WORKSHOP_BODY["name"] in names


def test_session_admin_mutation_without_the_csrf_header_is_refused(admin_client):
    response = admin_client.post("/api/admin/workshops", json=WORKSHOP_BODY)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "csrf_failed"


def test_delisted_admin_gets_not_admin_on_the_next_request(admin_client, monkeypatch):
    assert admin_client.get("/api/admin/workshops").status_code == 200
    monkeypatch.setenv("WORKSHOP0_ADMIN_EMAILS", "someone-else@example.test")
    reload_settings()
    for headers in ({}, {"X-Admin-Key": ""}):
        response = admin_client.get("/api/admin/workshops", headers=headers)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "not_admin"
    assert admin_client.get("/api/auth/me").json()["data"]["user"]["is_admin"] is False


def test_signed_in_non_admin_gets_not_admin(client):
    assert sign_in(client, "trainer@example.test").response.status_code == 303
    response = client.get("/api/admin/workshops", headers={"X-Admin-Key": ""})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "not_admin"


def test_key_admin_is_unchanged(client, make_client):
    ok_response = client.get("/api/admin/workshops", headers={"X-Admin-Key": TEST_ADMIN_KEY})
    assert ok_response.status_code == 200
    created = client.post(  # the key path needs no CSRF header
        "/api/admin/workshops", json=WORKSHOP_BODY, headers={"X-Admin-Key": TEST_ADMIN_KEY}
    )
    assert created.status_code == 200, created.text

    for headers in ({}, {"X-Admin-Key": ""}, {"X-Admin-Key": "wrong-key"}):
        response = make_client().get("/api/admin/workshops", headers=headers)
        assert response.status_code == 401
        assert response.json()["detail"] == KEY_FAILURE


def test_non_admin_session_with_a_wrong_key_keeps_the_key_failure(client):
    assert sign_in(client, "trainer2@example.test").response.status_code == 303
    response = client.get("/api/admin/workshops", headers={"X-Admin-Key": "wrong-key"})
    assert response.status_code == 401
    assert response.json()["detail"] == KEY_FAILURE


def test_admin_email_match_is_case_insensitive(client, monkeypatch):
    monkeypatch.setenv("WORKSHOP0_ADMIN_EMAILS", " Boss@Example.TEST , other@example.test")
    reload_settings()
    assert sign_in(client, "boss@example.test").response.status_code == 303
    assert client.get("/api/admin/workshops").status_code == 200
