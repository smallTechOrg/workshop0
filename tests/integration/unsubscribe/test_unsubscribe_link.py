from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from src.workshop0.db.models import AppUser, FacilitatorAction
from src.workshop0.db.session import create_db_session
from src.workshop0.services import email_prefs, unsubscribe


def _user(email="u@example.test"):
    with create_db_session() as s:
        u = AppUser(email=email, email_verified=True, display_name="U", oidc_issuer="i", oidc_subject=email)
        s.add(u)
        s.commit()
        return u.id


def _prefs(uid):
    with create_db_session() as s:
        p = email_prefs.get(s, uid)
        return p.alerts, p.digest


def test_token_roundtrip_and_url():
    tok = unsubscribe.make_token(7, "digest")
    assert unsubscribe.read_token(tok) == (7, "digest")
    u = unsubscribe.url("http://b.test/", 7, "alerts")
    assert u.startswith("http://b.test/api/email/unsubscribe?t=")
    assert unsubscribe.read_token(u.split("t=", 1)[1]) == (7, "alerts")


@pytest.mark.parametrize("bad", ["", "garbage", "abc.def.ghi", "a" * 500, "%%%", "ImFsZXJ0cyI.x"])
def test_bad_tokens_raise(bad):
    with pytest.raises(ValueError):
        unsubscribe.read_token(bad)


def test_tampered_and_wrong_secret_and_wrong_salt(monkeypatch):
    tok = unsubscribe.make_token(3, "alerts")
    with pytest.raises(ValueError):
        unsubscribe.read_token(tok[:-2] + ("AA" if tok[-2:] != "AA" else "BB"))
    from itsdangerous import URLSafeSerializer

    other_salt = URLSafeSerializer("unsub-test-secret-0123456789", salt="other").dumps([3, "alerts"])
    with pytest.raises(ValueError):
        unsubscribe.read_token(other_salt)
    bad_kind = URLSafeSerializer("unsub-test-secret-0123456789", salt=unsubscribe.SALT).dumps([3, "admin"])
    with pytest.raises(ValueError):
        unsubscribe.read_token(bad_kind)
    monkeypatch.setenv("WORKSHOP0_SESSION_SECRET", "different-secret")
    import src.workshop0.config.settings as m

    m._settings = None
    with pytest.raises(ValueError):
        unsubscribe.read_token(tok)


def test_blank_secret_rejects_everything(monkeypatch):
    tok = unsubscribe.make_token(3, "alerts")
    monkeypatch.setenv("WORKSHOP0_SESSION_SECRET", "")
    import src.workshop0.config.settings as m

    m._settings = None
    with pytest.raises(ValueError):
        unsubscribe.read_token(tok)


def test_make_token_rejects_unknown_kind():
    with pytest.raises(ValueError):
        unsubscribe.make_token(1, "admin")  # type: ignore[arg-type]


@pytest.mark.parametrize("kind,expect", [("alerts", (False, True)), ("digest", (True, False))])
def test_valid_link_flips_only_that_pref_idempotently(client, kind, expect):
    uid = _user()
    tok = unsubscribe.make_token(uid, kind)
    for _ in range(2):
        r = client.get(f"/api/email/unsubscribe?t={tok}", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == f"/app/network/unsubscribed/?kind={kind}"
        assert _prefs(uid) == expect
    with create_db_session() as s:
        rows = list(s.scalars(select(FacilitatorAction).where(FacilitatorAction.action == "email.unsubscribe")))
        assert rows and all(r.actor == "user" and json.loads(r.detail_json) == {"kind": kind} for r in rows)


def test_both_kinds_independent(client):
    uid = _user()
    for kind in ("alerts", "digest"):
        client.get(f"/api/email/unsubscribe?t={unsubscribe.make_token(uid, kind)}", follow_redirects=False)
    assert _prefs(uid) == (False, False)


@pytest.mark.parametrize("path", ["/api/email/unsubscribe", "/api/email/unsubscribe?t=", "/api/email/unsubscribe?t=junk"])
def test_invalid_links_redirect_never_error(client, path):
    uid = _user()
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/app/network/unsubscribed/?error=invalid_link"
    assert _prefs(uid) == (True, True)


def test_deleted_user_token_invalid(client):
    tok = unsubscribe.make_token(999999, "alerts")
    r = client.get(f"/api/email/unsubscribe?t={tok}", follow_redirects=False)
    assert r.headers["location"] == "/app/network/unsubscribed/?error=invalid_link"
    with create_db_session() as s:
        assert email_prefs.get(s, 999999).alerts is True


def test_no_auth_or_csrf_needed_and_url_helper_link_works(client):
    uid = _user()
    link = unsubscribe.url("http://base.test", uid, "alerts")
    r = client.get(link.replace("http://base.test", ""), follow_redirects=False)
    assert r.status_code == 303 and _prefs(uid) == (False, True)
