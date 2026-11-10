from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.workshop0.db.models import (
    AppUser, EmailOutbox, FacilitatorAction, Opportunity, OpportunityTopic, SavedSearch, Topic, TrainerProfile,
)
from src.workshop0.db.session import create_db_session
from src.workshop0.services import digest, email_prefs, unsubscribe

BASE = "http://base.test"
KEY = "cron-key-0123456789"
_n = [0]


@pytest.fixture(autouse=True)
def _cron(monkeypatch):
    monkeypatch.setenv("WORKSHOP0_CRON_KEY", KEY)
    import src.workshop0.config.settings as m

    m._settings = None


def _user(s, email, *, profile=True):
    _n[0] += 1
    u = AppUser(email=email, email_verified=True, display_name=email.split("@")[0], oidc_issuer="i", oidc_subject=f"s{_n[0]}")
    s.add(u)
    s.flush()
    if profile:
        s.add(TrainerProfile(user_id=u.id, headline="h", consent_at=datetime.now(timezone.utc), consent_version="v1"))
    s.flush()
    return u


def _search(s, u, criteria, name="S", enabled=True):
    s.add(SavedSearch(user_id=u.id, name=name, criteria_json=json.dumps(criteria), alerts_enabled=enabled))
    s.flush()


def _opp(s, *, slug_topic="python", published_days_ago=1, status="open", title=None, type_="workshop"):
    _n[0] += 1
    o = Opportunity(
        slug=f"opp-{_n[0]}", title=title or f"Listing {_n[0]}", type=type_, summary="s", location_mode="remote",
        locations_json="[]", status=status, deadline=datetime.now(timezone.utc) + timedelta(days=10),
        published_at=datetime.now(timezone.utc) - timedelta(days=published_days_ago),
        partner_display_name="Acme", partner_internal_name="SECRET Internal", internal_notes="SECRET",
    )
    s.add(o)
    s.flush()
    if slug_topic:
        s.add(OpportunityTopic(opportunity_id=o.id, topic_id=s.scalar(select(Topic.id).where(Topic.slug == slug_topic))))
    s.flush()
    return o


def _rows(s):
    return list(s.scalars(select(EmailOutbox).where(EmailOutbox.template == "network.digest").order_by(EmailOutbox.id)))


def _run(s, now=None):
    return digest.run_weekly(s, now=now or datetime.now(timezone.utc), base_url=BASE)


def test_iso_week_label_ist_boundaries():
    assert digest.iso_week_label(datetime(2026, 11, 10, 12, tzinfo=timezone.utc)) == "2026-W46"
    # Sunday 18:29 UTC = 23:59 IST (W46); 18:30 UTC = Monday 00:00 IST (W47)
    assert digest.iso_week_label(datetime(2026, 11, 15, 18, 29, tzinfo=timezone.utc)) == "2026-W46"
    assert digest.iso_week_label(datetime(2026, 11, 15, 18, 30, tzinfo=timezone.utc)) == "2026-W47"
    assert digest.iso_week_label(datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)) == "2026-W01"
    assert digest.iso_week_label(datetime(2027, 1, 1, 0, 0, tzinfo=timezone.utc)) == "2026-W53"
    assert digest.iso_week_label(datetime(2026, 3, 1)) == "2026-W09"  # naive treated as UTC


def test_happy_path_context_only_matching_and_no_leak():
    with create_db_session() as s:
        a = _user(s, "a@example.test")
        b = _user(s, "b@example.test")
        _search(s, a, {"topic_slugs": ["python"]}, enabled=False)  # alerts off still counts
        _search(s, b, {"types": ["role"]})
        o1 = _opp(s, title="Python one")
        _opp(s, title="Role only", type_="role", slug_topic=None)
        res = _run(s)
        assert res["enqueued"] == 2 and res["listings"] == 2 and res["week"].startswith("20")
        rows = {r.to_email: r for r in _rows(s)}
        ctx = json.loads(rows["a@example.test"].context_json)
        assert ctx["count"] == 1 and ctx["more"] == 0 and ctx["name"] == "a"
        assert [i["title"] for i in ctx["listings"]] == ["Python one"]
        assert set(ctx["listings"][0]) == {"title", "partner", "compensation", "cities", "url"}
        assert ctx["listings"][0]["url"] == f"{BASE}/opportunities/{o1.slug}"
        assert ctx["board_url"] == f"{BASE}/opportunities"
        assert ctx["manage_url"] == f"{BASE}/app/network/searches/"
        assert unsubscribe.read_token(ctx["unsubscribe_url"].split("t=")[1].replace("%3D", "=")) == (a.id, "digest")
        assert "SECRET" not in rows["a@example.test"].context_json
        assert [i["title"] for i in json.loads(rows["b@example.test"].context_json)["listings"]] == ["Role only"]
        assert rows["a@example.test"].dedupe_key == f"digest:{a.id}:{res['week']}"


def test_ordering_cap_and_more():
    with create_db_session() as s:
        u = _user(s, "a@example.test")
        _search(s, u, {"topic_slugs": ["python"]})
        for i in range(13):
            _opp(s, title=f"L{i}", published_days_ago=1 + i * 0.1)
        _run(s)
        (row,) = _rows(s)
        ctx = json.loads(row.context_json)
        assert ctx["count"] == 13 and ctx["more"] == 3 and len(ctx["listings"]) == 10
        assert ctx["listings"][0]["title"] == "L0"  # newest first


def test_second_run_same_week_adds_nothing():
    with create_db_session() as s:
        u = _user(s, "a@example.test")
        _search(s, u, {"topic_slugs": ["python"]})
        _opp(s)
        assert _run(s)["enqueued"] == 1
        assert _run(s)["enqueued"] == 0
        assert len(_rows(s)) == 1


def test_next_week_enqueues_again():
    with create_db_session() as s:
        u = _user(s, "a@example.test")
        _search(s, u, {"topic_slugs": ["python"]})
        o = _opp(s, published_days_ago=1)
        now = datetime.now(timezone.utc)
        assert _run(s, now)["enqueued"] == 1
        later = now + timedelta(days=1)
        # still inside 7-day window, different ISO week unless same; force a different week
        while digest.iso_week_label(later) == digest.iso_week_label(now):
            later += timedelta(days=1)
        o.published_at = later - timedelta(hours=1)
        o.deadline = later + timedelta(days=5)
        s.flush()
        assert _run(s, later)["enqueued"] == 1


def test_exclusions():
    with create_db_session() as s:
        optout = _user(s, "optout@example.test")
        noprofile = _user(s, "noprof@example.test", profile=False)
        nosearch = _user(s, "nosearch@example.test")
        nomatch = _user(s, "nomatch@example.test")
        ok = _user(s, "ok@example.test")
        for u in (optout, noprofile, ok):
            _search(s, u, {"topic_slugs": ["python"]})
        _search(s, nomatch, {"types": ["role"]})
        email_prefs.set_prefs(s, optout.id, digest=False)
        _opp(s)
        _opp(s, published_days_ago=8, title="old")
        _opp(s, status="draft", title="draft")
        _opp(s, status="closed", title="closed")
        res = _run(s)
        assert res["enqueued"] == 1 and res["listings"] == 1
        assert [r.to_email for r in _rows(s)] == ["ok@example.test"]
        del nosearch


def test_alerts_off_does_not_block_digest_but_digest_off_does():
    with create_db_session() as s:
        u = _user(s, "a@example.test")
        _search(s, u, {"topic_slugs": ["python"]})
        _opp(s)
        email_prefs.set_prefs(s, u.id, alerts=False)
        assert _run(s)["enqueued"] == 1


def test_expired_listing_excluded():
    with create_db_session() as s:
        u = _user(s, "a@example.test")
        _search(s, u, {"topic_slugs": ["python"]})
        o = _opp(s)
        o.deadline = datetime.now(timezone.utc) - timedelta(hours=1)
        s.flush()
        res = _run(s)
        assert res == {"enqueued": 0, "week": res["week"], "listings": 0}


def test_no_listings_zero():
    with create_db_session() as s:
        _user(s, "a@example.test")
        assert _run(s)["enqueued"] == 0


# ---- endpoint ----

def test_endpoint_key_unset_is_404_whatever(client, monkeypatch):
    monkeypatch.setenv("WORKSHOP0_CRON_KEY", "")
    import src.workshop0.config.settings as m

    m._settings = None
    for headers in ({}, {"X-Cron-Key": KEY}, {"X-Cron-Key": ""}):
        r = client.post("/api/cron/weekly-digest", headers=headers)
        assert r.status_code == 404 and r.json()["detail"]["code"] == "not_found"


def test_endpoint_wrong_or_missing_key_401_and_query_key_ignored(client):
    for headers in ({}, {"X-Cron-Key": "nope"}, {"X-Cron-Key": ""}, {"X-Cron-Key": KEY + "x"}):
        r = client.post("/api/cron/weekly-digest", headers=headers)
        assert r.status_code == 401 and r.json()["detail"]["code"] == "invalid_cron_key"
    assert client.post(f"/api/cron/weekly-digest?x_cron_key={KEY}&key={KEY}").status_code == 401
    assert client.get("/api/cron/weekly-digest", headers={"X-Cron-Key": KEY}).status_code == 405
    with create_db_session() as s:
        assert _rows(s) == []


def test_endpoint_runs_audits_idempotent_and_never_leaks_key(client):
    with create_db_session() as s:
        u = _user(s, "a@example.test")
        _search(s, u, {"topic_slugs": ["python"]})
        _opp(s)
        s.commit()
    r = client.post("/api/cron/weekly-digest", headers={"X-Cron-Key": KEY})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["enqueued"] == 1 and d["listings"] == 1 and "-W" in d["week"]
    assert KEY not in r.text
    r2 = client.post("/api/cron/weekly-digest", headers={"X-Cron-Key": KEY})
    assert r2.json()["data"]["enqueued"] == 0
    with create_db_session() as s:
        audits = list(s.scalars(select(FacilitatorAction).where(FacilitatorAction.action == "cron.weekly_digest")))
        assert len(audits) == 2 and all(a.actor == "cron" for a in audits)
        assert json.loads(audits[0].detail_json) == d
        assert KEY not in "".join(a.detail_json for a in audits)
        assert len(_rows(s)) == 1


def test_endpoint_empty_db_ok(client):
    r = client.post("/api/cron/weekly-digest", headers={"X-Cron-Key": KEY})
    assert r.status_code == 200 and r.json()["data"]["enqueued"] == 0
