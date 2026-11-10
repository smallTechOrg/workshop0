"""A2: creating/updating a listing into effective-open enqueues alerts in the same transaction."""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from src.workshop0.db.models import AppUser, EmailOutbox, SavedSearch, TrainerProfile
from src.workshop0.db.session import create_db_session
from tests.conftest import iso, opportunity_body

_n = [0]


def _subscriber(email="asha@example.test", criteria=None):
    _n[0] += 1
    with create_db_session() as s:
        u = AppUser(email=email, email_verified=True, display_name="Asha",
                    oidc_issuer="iss", oidc_subject=f"hook{_n[0]}")
        s.add(u)
        s.flush()
        s.add(TrainerProfile(user_id=u.id, headline="h", consent_at=datetime.now(timezone.utc),
                             consent_version="v1"))
        s.add(SavedSearch(user_id=u.id, name="All workshops",
                          criteria_json=json.dumps(criteria or {"types": ["workshop"]}),
                          alerts_enabled=True))
        s.commit()
        return u.id


def _alerts():
    with create_db_session() as s:
        return [r for r in s.scalars(select(EmailOutbox).order_by(EmailOutbox.id))
                if r.template == "network.alert"]


def _post(client, admin_headers, topic_ids, **kw):
    return client.post("/api/admin/opportunities", headers=admin_headers,
                       json=opportunity_body([topic_ids["generative-ai"]], **kw))


def test_create_open_enqueues_and_schedules_drain(client, admin_headers, topic_ids, drains):
    uid = _subscriber()
    r = _post(client, admin_headers, topic_ids, status="open")
    assert r.status_code == 200, r.text
    opp = r.json()["data"]["opportunity"]
    (row,) = _alerts()
    assert row.dedupe_key == f"alert:{opp['id']}:{uid}"
    assert "Acme Payments" not in row.context_json and "R. Rao" not in row.context_json
    assert drains == [100]


def test_create_draft_does_nothing(client, admin_headers, topic_ids, drains):
    _subscriber()
    assert _post(client, admin_headers, topic_ids, status="draft").status_code == 200
    assert _alerts() == [] and drains == []


def test_create_closed_does_nothing(client, admin_headers, topic_ids, drains):
    _subscriber()
    assert _post(client, admin_headers, topic_ids, status="closed").status_code == 200
    assert _alerts() == [] and drains == []


def test_patch_draft_to_open_enqueues_once_and_later_edits_do_not(client, admin_headers, topic_ids, drains):
    _subscriber()
    opp = _post(client, admin_headers, topic_ids).json()["data"]["opportunity"]
    url = f"/api/admin/opportunities/{opp['id']}"
    assert client.patch(url, json={"title": "Renamed listing"}, headers=admin_headers).status_code == 200
    assert _alerts() == [] and drains == []
    assert client.patch(url, json={"status": "open"}, headers=admin_headers).status_code == 200
    assert len(_alerts()) == 1 and drains == [100]
    # already open: edit, noop, close - no further rows or drains
    client.patch(url, json={"title": "Renamed again"}, headers=admin_headers)
    client.patch(url, json={"title": "Renamed again"}, headers=admin_headers)
    client.patch(url, json={"status": "closed"}, headers=admin_headers)
    assert len(_alerts()) == 1 and drains == [100]


def test_reopen_closed_listing_is_deduped(client, admin_headers, topic_ids, drains):
    _subscriber()
    opp = _post(client, admin_headers, topic_ids, status="open").json()["data"]["opportunity"]
    url = f"/api/admin/opportunities/{opp['id']}"
    client.patch(url, json={"status": "closed"}, headers=admin_headers)
    client.patch(url, json={"status": "open"}, headers=admin_headers)
    assert len(_alerts()) == 1  # dedupe key alert:<opp>:<user>
    assert drains == [100, 100]  # transition still schedules a drain


def test_expired_to_open_via_new_deadline_enqueues(client, admin_headers, topic_ids, drains):
    _subscriber()
    opp = _post(client, admin_headers, topic_ids).json()["data"]["opportunity"]
    oid = opp["id"]
    with create_db_session() as s:
        s.execute(text("UPDATE opportunity SET status='open', deadline=:d WHERE id=:i"),
                  {"d": datetime.now(timezone.utc) - timedelta(days=1), "i": oid})
        s.commit()
    new_deadline = iso(datetime.now(timezone.utc) + timedelta(days=5))
    r = client.patch(f"/api/admin/opportunities/{oid}", json={"deadline": new_deadline}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["opportunity"]["status"] == "open"
    assert len(_alerts()) == 1 and drains == [100]


def test_non_matching_search_enqueues_nothing_but_still_drains(client, admin_headers, topic_ids, drains):
    _subscriber(criteria={"types": ["role"]})
    assert _post(client, admin_headers, topic_ids, status="open").status_code == 200
    assert _alerts() == []


def test_enqueue_failure_is_swallowed_and_write_commits(client, admin_headers, topic_ids, drains, monkeypatch):
    from src.workshop0.services import alerts

    def boom(*a, **k):
        raise RuntimeError("nope")

    monkeypatch.setattr(alerts, "enqueue_alerts_for", boom)
    r = _post(client, admin_headers, topic_ids, status="open")
    assert r.status_code == 200, r.text
    oid = r.json()["data"]["opportunity"]["id"]
    got = client.get(f"/api/admin/opportunities/{oid}", headers=admin_headers)
    assert got.json()["data"]["opportunity"]["stored_status"] == "open"
    assert _alerts() == []


def test_failed_enqueue_rolls_back_partial_rows_via_savepoint(client, admin_headers, topic_ids, drains, monkeypatch):
    from src.workshop0.email import outbox
    from src.workshop0.services import alerts

    _subscriber()

    def partial(session, opp, *, base_url):
        outbox.enqueue(session, to="x@example.test", template="network.alert", context={}, dedupe_key="partial")
        raise RuntimeError("after one row")

    monkeypatch.setattr(alerts, "enqueue_alerts_for", partial)
    assert _post(client, admin_headers, topic_ids, status="open").status_code == 200
    with create_db_session() as s:
        assert s.scalar(select(EmailOutbox.id).where(EmailOutbox.dedupe_key == "partial")) is None


def test_validation_failure_enqueues_nothing(client, admin_headers, topic_ids, drains):
    _subscriber()
    r = _post(client, admin_headers, topic_ids, status="open", title="x")
    assert r.status_code == 422
    assert _alerts() == [] and drains == []
