"""Phase 13 S0: services/email_prefs (no row = both on; upsert; never commits)."""

from datetime import datetime, timezone

from src.workshop0.db.models import AppUser, EmailPref
from src.workshop0.db.session import _get_session_factory
from src.workshop0.services import email_prefs
from src.workshop0.services.email_prefs import EmailPrefs


def _user(session, n: int) -> int:
    user = AppUser(
        email=f"prefs{n}@example.test",
        email_verified=True,
        display_name=f"Prefs {n}",
        oidc_issuer="https://accounts.google.com",
        oidc_subject=f"sub-prefs-{n}",
        created_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()
    return user.id


def test_missing_row_means_both_on_and_batch_matches():
    with _get_session_factory()() as s:
        a, b = _user(s, 1), _user(s, 2)
        s.commit()
        assert email_prefs.get(s, a) == EmailPrefs(True, True)
        email_prefs.set_prefs(s, b, alerts=False)
        s.commit()
        got = email_prefs.prefs_for(s, [a, b, b])
        assert got == {a: EmailPrefs(True, True), b: EmailPrefs(False, True)}
        assert email_prefs.prefs_for(s, []) == {}


def test_set_prefs_is_partial_upsert_and_unchanged_by_none():
    with _get_session_factory()() as s:
        uid = _user(s, 3)
        s.commit()
        assert email_prefs.set_prefs(s, uid, digest=False) == EmailPrefs(True, False)
        assert email_prefs.set_prefs(s, uid) == EmailPrefs(True, False)
        assert email_prefs.set_prefs(s, uid, alerts=False, digest=True) == EmailPrefs(False, True)
        s.commit()
        assert s.query(EmailPref).count() == 1


def test_set_prefs_does_not_commit():
    with _get_session_factory()() as s:
        uid = _user(s, 4)
        s.commit()
        email_prefs.set_prefs(s, uid, alerts=False)
        s.rollback()
        assert email_prefs.get(s, uid) == EmailPrefs(True, True)
