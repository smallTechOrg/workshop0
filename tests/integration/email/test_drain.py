"""drain(): real SMTP over a socket to the in-process aiosmtpd sink (never a real server)."""

from __future__ import annotations

import logging

from sqlalchemy import select

from src.workshop0.db.models import EmailOutbox
from src.workshop0.db.session import create_db_session
from src.workshop0.email import sender
from src.workshop0.email.outbox import enqueue

CTX = {"name": "Asha", "title": "T", "url": "http://base.test/opportunities/t",
       "applications_url": "http://base.test/app/network/applications/", "status": "shortlisted"}


def _enqueue(to="asha@example.test", key=None, template="application.status_changed"):
    with create_db_session() as s:
        row = enqueue(s, to=to, template=template, context=CTX, dedupe_key=key)
        s.flush()
        return row.id


def _row(row_id) -> EmailOutbox:
    with create_db_session() as s:
        return s.get(EmailOutbox, row_id)


def test_sent_over_smtp_multipart_with_absolute_links(smtp_env):
    rid = _enqueue()
    assert sender.drain() == 1
    row = _row(rid)
    assert row.status == "sent" and row.sent_at and row.attempts == 1 and row.subject
    assert len(smtp_env.messages) == 1
    msg = smtp_env.messages[0]
    assert msg["To"] == "asha@example.test" and msg["Subject"] == row.subject
    parts = {p.get_content_type(): p.get_payload(decode=True).decode() for p in msg.walk() if not p.is_multipart()}
    assert set(parts) == {"text/plain", "text/html"}
    assert "http://base.test/opportunities/t" in parts["text/plain"]
    assert "<img" not in parts["text/html"]


def test_unconfigured_smtp_records_rows_and_never_fails():
    rid = _enqueue()
    assert sender.drain() == 1
    row = _row(rid)
    assert row.status == "recorded" and row.sent_at is None and row.subject


def test_empty_queue_and_dedupe(smtp_env):
    assert sender.drain() == 0
    a = _enqueue(key="k1")
    b = _enqueue(key="k1")
    assert a == b
    sender.drain()
    sender.drain()
    assert len(smtp_env.messages) == 1


def test_eleventh_email_to_one_recipient_is_rate_limited(smtp_env):
    ids = [_enqueue(to="busy@example.test", key=f"k{i}") for i in range(11)]
    sender.drain(limit=50)
    rows = [_row(i) for i in ids]
    assert [r.status for r in rows].count("sent") == 10
    assert rows[-1].status == "recorded" and rows[-1].last_error == "rate_limited"
    assert len(smtp_env.messages) == 10


def test_failing_smtp_fails_after_three_attempts_then_retry_succeeds(
    smtp_env, client, admin_headers
):
    smtp_env.fail_next(3)
    rid = _enqueue()
    sender.drain()
    row = _row(rid)
    assert row.status == "failed" and row.attempts == 3 and row.last_error
    assert "fake-test-password" not in row.last_error
    assert smtp_env.messages == []

    r = client.post(f"/api/admin/outbox/{rid}/retry", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["outbox"]["status"] == "sent"
    assert len(smtp_env.messages) == 1


def test_closed_port_fails_and_password_never_logged(smtp_env, caplog, capsys):
    import src.workshop0.config.settings as sm

    smtp_env.stop()
    sm._settings = None
    rid = _enqueue()
    with caplog.at_level(logging.DEBUG):
        sender.drain()
    row = _row(rid)
    assert row.status == "failed" and row.attempts == 3
    out = capsys.readouterr()
    assert "fake-test-password" not in caplog.text + out.out + out.err + (row.last_error or "")


def test_bad_context_template_fails_permanently(smtp_env):
    with create_db_session() as s:
        row = EmailOutbox(to_email="x@example.test", template="bogus", context_json="{}",
                          status="queued", attempts=0)
        s.add(row)
        s.flush()
        rid = row.id
    sender.drain()
    assert _row(rid).status == "failed"


def test_rate_limit_reads_real_settings_names(smtp_env, monkeypatch):
    import src.workshop0.config.settings as settings_module

    monkeypatch.setenv("WORKSHOP0_EMAIL_RATE_PER_RECIPIENT", "2")
    settings_module._settings = None
    ids = [_enqueue(to="busy@example.test", key=f"r{i}") for i in range(3)]
    sender.drain(limit=50)
    assert [_row(i).status for i in ids] == ["sent", "sent", "recorded"]
    assert len(smtp_env.messages) == 2

    monkeypatch.setenv("WORKSHOP0_EMAIL_RATE_GLOBAL", "3")
    monkeypatch.setenv("WORKSHOP0_EMAIL_RATE_PER_RECIPIENT", "50")
    settings_module._settings = None
    more = [_enqueue(to=f"u{i}@example.test", key=f"g{i}") for i in range(3)]
    sender.drain(limit=50)
    assert [_row(i).status for i in more] == ["sent", "recorded", "recorded"]


def test_drain_without_smtp_env_records_and_opens_no_socket(monkeypatch):
    import socket

    from src.workshop0.config.settings import get_settings

    # .env (real creds locally) must not leak through: env vars blanked by the root conftest win
    assert not get_settings().smtp_configured

    def _boom(*a, **k):
        raise AssertionError("socket opened during a test without smtp_env")

    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(socket.socket, "connect", _boom)
    rid = _enqueue()
    assert sender.drain() == 1
    row = _row(rid)
    assert row.status == "recorded" and row.sent_at is None and row.attempts == 0


def test_concurrent_drains_never_send_a_row_twice(smtp_env, monkeypatch):
    """A batch claim + per-row commit used to release the remaining locks, letting a second
    drain re-send them. Each row must be claimed in its own transaction."""
    import threading
    import time

    from src.workshop0.email import smtp as smtp_mod

    monkeypatch.setattr(sender, "_rate_limited", lambda session, to: False)
    ids = [_enqueue(to=f"c{i}@example.test", key=f"conc-{i}") for i in range(6)]
    real_send = smtp_mod.send

    def slow_send(*a, **kw):
        time.sleep(0.15)
        return real_send(*a, **kw)

    monkeypatch.setattr(smtp_mod, "send", slow_send)
    first = threading.Thread(target=sender.drain)
    first.start()
    time.sleep(0.25)  # the first drain has committed row 1 and is mid-send on row 2
    second = threading.Thread(target=sender.drain)
    second.start()
    first.join()
    second.join()
    assert sorted(m["To"] for m in smtp_env.messages) == sorted(f"c{i}@example.test" for i in range(6))
    assert all(_row(i).status == "sent" for i in ids)


def test_list_unsubscribe_headers_only_on_mail_with_an_unsubscribe_link(smtp_env):
    alert_ctx = {"name": "Asha", "title": "T", "partner": "P", "compensation": "C", "cities": "Pune",
                 "url": "http://base.test/opportunities/t", "search_names": "S",
                 "unsubscribe_url": "http://base.test/api/email/unsubscribe?t=tok123",
                 "manage_url": "http://base.test/app/network/searches/"}
    with create_db_session() as s:
        enqueue(s, to="lu@example.test", template="network.alert", context=alert_ctx, dedupe_key="lu-alert")
        s.commit()
    _enqueue(to="plain@example.test", key="lu-plain")
    sender.drain()
    by_to = {m["To"]: m for m in smtp_env.messages}
    alert = by_to["lu@example.test"]
    assert alert["List-Unsubscribe"] == "<http://base.test/api/email/unsubscribe?t=tok123>"
    assert alert["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    plain = by_to["plain@example.test"]
    assert plain["List-Unsubscribe"] is None and plain["List-Unsubscribe-Post"] is None
