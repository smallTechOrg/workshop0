"""GET /api/admin/outbox and POST …/retry."""

from __future__ import annotations

from src.workshop0.db.models import EmailOutbox
from src.workshop0.db.session import create_db_session
from src.workshop0.email.outbox import enqueue


def _queue(n=1):
    with create_db_session() as s:
        for i in range(n):
            enqueue(s, to=f"u{i}@example.test", template="network.welcome",
                    context={"name": "U", "applications_url": "http://base.test/app/network/applications/"},
                    dedupe_key=f"w{i}")


def test_requires_admin_key(client):
    assert client.get("/api/admin/outbox").status_code == 401


def test_unconfigured_lists_recorded_rows_with_flag(client, admin_headers):
    _queue(2)
    r = client.get("/api/admin/outbox", headers=admin_headers)  # page load drains
    data = r.json()["data"]
    assert data["smtp_configured"] is False and data["total"] == 2
    assert {i["status"] for i in data["items"]} == {"recorded"}
    assert "password" not in r.text.lower()


def test_configured_flag_and_sent_filter(client, admin_headers, smtp_env):
    _queue(1)
    data = client.get("/api/admin/outbox?status=sent", headers=admin_headers).json()["data"]
    assert data["smtp_configured"] is True and data["total"] == 1
    assert client.get("/api/admin/outbox?status=recorded", headers=admin_headers).json()["data"]["total"] == 0
    assert "fake-test-password" not in client.get("/api/admin/outbox", headers=admin_headers).text


def test_bad_status_is_422_and_unknown_retry_404(client, admin_headers):
    assert client.get("/api/admin/outbox?status=bogus", headers=admin_headers).status_code == 422
    assert client.post("/api/admin/outbox/999/retry", headers=admin_headers).status_code == 404


def test_retry_only_failed(client, admin_headers):
    _queue(1)
    client.get("/api/admin/outbox", headers=admin_headers)
    with create_db_session() as s:
        rid = s.query(EmailOutbox).one().id
    assert client.post(f"/api/admin/outbox/{rid}/retry", headers=admin_headers).status_code == 409
