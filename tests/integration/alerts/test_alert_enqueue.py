from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from src.workshop0.db.models import (
    AppUser, EmailOutbox, Opportunity, OpportunityTopic, SavedSearch, Topic, TrainerProfile,
)
from src.workshop0.db.session import create_db_session
from src.workshop0.services import alerts, email_prefs

BASE = "http://base.test"
_n = [0]


def _user(s, email, *, profile=True, name=None):
    _n[0] += 1
    u = AppUser(
        email=email, email_verified=True, display_name=name or email.split("@")[0],
        oidc_issuer="iss", oidc_subject=f"sub{_n[0]}",
    )
    s.add(u)
    s.flush()
    if profile:
        s.add(TrainerProfile(user_id=u.id, headline="h", consent_at=datetime.now(timezone.utc), consent_version="v1"))
    s.flush()
    return u


def _search(s, user, name, criteria, enabled=True):
    s.add(SavedSearch(user_id=user.id, name=name, criteria_json=json.dumps(criteria), alerts_enabled=enabled))
    s.flush()


def _opp(s, *, slugs=("python",), status="open", days=5, **kw):
    _n[0] += 1
    o = Opportunity(
        slug=f"opp-{_n[0]}", title="Python for ops", type="workshop", summary="s", location_mode="remote",
        locations_json="[]", status=status, deadline=datetime.now(timezone.utc) + timedelta(days=days),
        partner_display_name="Acme Display", partner_internal_name="SECRET Internal Ltd",
        internal_notes="SECRET note", compensation_min=5000, compensation_max=8000,
        compensation_currency="INR", compensation_unit="day", **kw,
    )
    s.add(o)
    s.flush()
    for slug in slugs:
        tid = s.scalar(select(Topic.id).where(Topic.slug == slug))
        s.add(OpportunityTopic(opportunity_id=o.id, topic_id=tid))
    s.flush()
    return o


def _rows(s):
    return list(s.scalars(select(EmailOutbox).order_by(EmailOutbox.id)))


def test_happy_path_context_and_dedupe():
    with create_db_session() as s:
        u = _user(s, "asha@example.test", name="Asha")
        _search(s, u, "Python stuff", {"topic_slugs": ["python"]})
        o = _opp(s)
        assert alerts.enqueue_alerts_for(s, o, base_url=BASE) == 1
        (row,) = _rows(s)
        assert row.template == "network.alert" and row.to_email == "asha@example.test"
        assert row.dedupe_key == f"alert:{o.id}:{u.id}" and row.status == "queued"
        ctx = json.loads(row.context_json)
        assert ctx == {
            "name": "Asha", "title": "Python for ops", "partner": "Acme Display",
            "compensation": "₹5,000–8,000 per day", "cities": "Remote", "url": f"{BASE}/opportunities/{o.slug}",
            "search_names": "Python stuff",
            "unsubscribe_url": f"{BASE}/api/email/unsubscribe?t=tok-{u.id}-alerts",
            "manage_url": f"{BASE}/app/network/searches/",
        }
        assert "SECRET" not in row.context_json
        # second run: no new rows
        assert alerts.enqueue_alerts_for(s, o, base_url=BASE) == 0
        assert len(_rows(s)) == 1


def test_two_matching_searches_one_email_naming_both():
    with create_db_session() as s:
        u = _user(s, "a@example.test")
        _search(s, u, "First", {"types": ["workshop"]})
        _search(s, u, "Second", {"topic_slugs": ["python"]})
        _search(s, u, "Third", {"types": ["role"]})
        o = _opp(s)
        assert alerts.enqueue_alerts_for(s, o, base_url=BASE) == 1
        (row,) = _rows(s)
        assert json.loads(row.context_json)["search_names"] == "First, Second"


def test_gating_consent_prefs_enabled():
    with create_db_session() as s:
        no_profile = _user(s, "np@example.test", profile=False)
        _search(s, no_profile, "n", {"types": ["workshop"]})
        off_search = _user(s, "os@example.test")
        _search(s, off_search, "n", {"types": ["workshop"]}, enabled=False)
        off_pref = _user(s, "op@example.test")
        _search(s, off_pref, "n", {"types": ["workshop"]})
        email_prefs.set_prefs(s, off_pref.id, alerts=False)
        digest_off = _user(s, "do@example.test")  # digest off must NOT stop alerts
        _search(s, digest_off, "n", {"types": ["workshop"]})
        email_prefs.set_prefs(s, digest_off.id, digest=False)
        nomatch = _user(s, "nm@example.test")
        _search(s, nomatch, "n", {"types": ["role"]})
        mixed = _user(s, "mx@example.test")  # one disabled + one enabled search
        _search(s, mixed, "off", {"types": ["workshop"]}, enabled=False)
        _search(s, mixed, "on", {"topic_slugs": ["python"]})
        o = _opp(s)
        assert alerts.enqueue_alerts_for(s, o, base_url=BASE) == 2
        assert sorted(r.to_email for r in _rows(s)) == ["do@example.test", "mx@example.test"]
        assert json.loads(next(r for r in _rows(s) if r.to_email == "mx@example.test").context_json)[
            "search_names"
        ] == "on"


def test_non_open_listings_enqueue_nothing():
    with create_db_session() as s:
        u = _user(s, "a@example.test")
        _search(s, u, "n", {"types": ["workshop"]})
        assert alerts.enqueue_alerts_for(s, _opp(s, status="draft"), base_url=BASE) == 0
        assert alerts.enqueue_alerts_for(s, _opp(s, status="closed"), base_url=BASE) == 0
        assert alerts.enqueue_alerts_for(s, _opp(s, days=-1), base_url=BASE) == 0  # expired
        assert _rows(s) == []


def test_no_searches_and_corrupt_criteria_are_harmless():
    with create_db_session() as s:
        o = _opp(s)
        assert alerts.enqueue_alerts_for(s, o, base_url=BASE) == 0
        u = _user(s, "a@example.test")
        s.add(SavedSearch(user_id=u.id, name="bad", criteria_json="{not json", alerts_enabled=True))
        s.add(SavedSearch(user_id=u.id, name="list", criteria_json="[1]", alerts_enabled=True))
        s.flush()
        assert alerts.enqueue_alerts_for(s, o, base_url=BASE) == 0


def test_pre_existing_dedupe_key_counts_zero_and_other_users_still_enqueue():
    with create_db_session() as s:
        a = _user(s, "a@example.test")
        b = _user(s, "b@example.test")
        for u in (a, b):
            _search(s, u, "n", {"types": ["workshop"]})
        o = _opp(s)
        from src.workshop0.email import outbox

        outbox.enqueue(s, to=a.email, template="network.alert", context={}, dedupe_key=f"alert:{o.id}:{a.id}")
        assert alerts.enqueue_alerts_for(s, o, base_url=BASE) == 1
        assert len(_rows(s)) == 2


def test_enqueue_does_not_commit():
    with create_db_session() as s:
        u = _user(s, "a@example.test")
        _search(s, u, "n", {"types": ["workshop"]})
        o = _opp(s)
        alerts.enqueue_alerts_for(s, o, base_url=BASE)
        s.rollback()
        assert _rows(s) == []
