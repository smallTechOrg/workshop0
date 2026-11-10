"""C14 admin side: pipeline list, bulk status (audit + outbox + dedupe + consent), CSV."""

from __future__ import annotations

from sqlalchemy import select, text

from src.workshop0.db.models import Application
from tests.integration.applications.conftest import (
    apply_to,
    audit_rows,
    ctx,
    db,
    outbox_rows,
)
import json


def move(client, headers, opp_id, ids, status, notify=True):
    return client.post(
        f"/api/admin/opportunities/{opp_id}/applications/status",
        json={"application_ids": ids, "status": status, "notify": notify},
        headers=headers,
    )


def seed_applicants(trainer_factory, listing_id: int, n: int) -> list[int]:
    ids = []
    for i in range(n):
        _, tc, _ = trainer_factory(f"trainer{i:02d}@example.test")
        ids.append(apply_to(tc, listing_id, f"note {i}").json()["data"]["application"]["id"])
    return ids


def test_admin_endpoints_require_the_key(client, open_listing):
    listing = open_listing()
    base = f"/api/admin/opportunities/{listing['id']}/applications"
    assert client.get(base).status_code == 401
    assert client.get(base + ".csv").status_code == 401
    assert client.post(base + "/status", json={}).status_code == 401


def test_pipeline_list_filter_counts_and_pagination(client, admin_headers, trainer_factory, open_listing):
    listing = open_listing()
    ids = seed_applicants(trainer_factory, listing["id"], 5)
    move(client, admin_headers, listing["id"], ids[:2], "shortlisted", notify=False)
    base = f"/api/admin/opportunities/{listing['id']}/applications"
    data = client.get(base, headers=admin_headers).json()["data"]
    assert data["total"] == 5 and data["counts"]["shortlisted"] == 2 and data["counts"]["applied"] == 3
    row = data["applications"][0]
    assert row["note"] == "note 0" and row["source"] == "self" and row["trainer"]["email"] == "trainer00@example.test"
    only = client.get(base + "?status=shortlisted", headers=admin_headers).json()["data"]
    assert only["total"] == 2 and {a["status"] for a in only["applications"]} == {"shortlisted"}
    page2 = client.get(base + "?page=2&page_size=2", headers=admin_headers).json()["data"]
    assert len(page2["applications"]) == 2 and page2["total_pages"] == 3
    assert client.get(base + "?status=bogus", headers=admin_headers).status_code == 422
    assert client.get(base + "?page=0", headers=admin_headers).status_code == 422


def test_pipeline_unknown_listing_404_and_empty_listing(client, admin_headers, open_listing):
    assert client.get("/api/admin/opportunities/99999/applications", headers=admin_headers).status_code == 404
    assert client.get("/api/admin/opportunities/abc/applications", headers=admin_headers).status_code == 404
    listing = open_listing()
    data = client.get(f"/api/admin/opportunities/{listing['id']}/applications", headers=admin_headers).json()["data"]
    assert data["applications"] == [] and data["total"] == 0 and data["total_pages"] == 0


def test_bulk_move_12_one_audit_row_12_emails_and_rerun_dedupes(
    client, admin_headers, trainer_factory, open_listing
):
    listing = open_listing()
    ids = seed_applicants(trainer_factory, listing["id"], 12)
    r = move(client, admin_headers, listing["id"], ids, "shortlisted")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["emails_queued"] == 12
    audit = audit_rows("application.status")
    assert len(audit) == 1
    detail = json.loads(audit[0].detail_json)
    assert sorted(detail["application_ids"]) == sorted(ids) and detail["to_status"] == "shortlisted"
    assert audit[0].subject_type == "opportunity"
    mail = outbox_rows("application.status_changed")
    assert len(mail) == 12 and len({m.dedupe_key for m in mail}) == 12
    assert {m.dedupe_key for m in mail} == {f"status:{i}:shortlisted" for i in ids}
    c = ctx(mail[0])
    assert c["status"] == "shortlisted" and c["status_label"] == "Shortlisted"
    assert c["url"] == f"http://testserver/opportunities/{listing['slug']}"
    assert c["applications_url"] == "http://testserver/app/network/applications/"

    again = move(client, admin_headers, listing["id"], ids, "shortlisted")  # re-run
    assert again.status_code == 200 and again.json()["data"]["changed"] == []
    assert len(outbox_rows("application.status_changed")) == 12
    assert len(audit_rows("application.status")) == 1  # nothing changed -> no new audit row

    # applied -> shortlisted again re-uses the dedupe key: still 12 rows
    move(client, admin_headers, listing["id"], ids, "applied", notify=False)
    move(client, admin_headers, listing["id"], ids, "shortlisted")
    assert len(outbox_rows("application.status_changed")) == 12


def test_notify_false_sends_nothing_but_audits(client, admin_headers, trainer_factory, open_listing):
    listing = open_listing()
    ids = seed_applicants(trainer_factory, listing["id"], 2)
    r = move(client, admin_headers, listing["id"], ids, "selected", notify=False)
    assert r.json()["data"]["emails_queued"] == 0
    assert outbox_rows("application.status_changed") == []
    assert len(audit_rows("application.status")) == 1


def test_trainer_sees_new_status(client, admin_headers, trainer_factory, open_listing):
    _, tclient, _ = trainer_factory("ada@example.test")
    listing = open_listing()
    app_id = apply_to(tclient, listing["id"]).json()["data"]["application"]["id"]
    move(client, admin_headers, listing["id"], [app_id], "not_selected")
    mine = tclient.get("/api/me/applications").json()["data"]["applications"][0]
    assert mine["status"] == "not_selected"


def test_consent_gating_skips_email_and_notes_it_in_audit(
    client, admin_headers, trainer_factory, open_listing
):
    listing = open_listing()
    ids = seed_applicants(trainer_factory, listing["id"], 2)
    # consent_at is NOT NULL in the schema, so simulate "no consent" by patching the check input
    from src.workshop0.db.models import TrainerProfile

    with db() as session:
        app = session.get(Application, ids[0])
        profile = session.get(TrainerProfile, app.profile_id)
        # consent_at is NOT NULL in the schema: relax it in the test DB for this test only
        # and restore it afterwards, so the null-consent gate is exercised for real.
        session.execute(text("ALTER TABLE trainer_profile ALTER COLUMN consent_at DROP NOT NULL"))
        profile.consent_at = None
        session.commit()
    try:
        r = move(client, admin_headers, listing["id"], ids, "shortlisted")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["emails_queued"] == 1 and data["skipped_no_consent"] == [ids[0]]
        mail = outbox_rows("application.status_changed")
        assert len(mail) == 1 and mail[0].dedupe_key == f"status:{ids[1]}:shortlisted"
        detail = json.loads(audit_rows("application.status")[0].detail_json)
        assert detail["skipped_no_consent"] == [ids[0]]
        assert sorted(detail["application_ids"]) == sorted(ids)  # the move itself still happened
    finally:
        with db() as session:
            session.execute(text("UPDATE trainer_profile SET consent_at = now() WHERE consent_at IS NULL"))
            session.execute(text("ALTER TABLE trainer_profile ALTER COLUMN consent_at SET NOT NULL"))
            session.commit()


def test_bulk_validation_errors(client, admin_headers, trainer_factory, open_listing):
    listing = open_listing()
    other = open_listing(title="Another listing entirely")
    ids = seed_applicants(trainer_factory, listing["id"], 2)
    url = f"/api/admin/opportunities/{listing['id']}/applications/status"
    for body in (
        {"application_ids": [], "status": "shortlisted"},
        {"application_ids": ids, "status": "withdrawn"},
        {"application_ids": ids, "status": "nonsense"},
        {"application_ids": list(range(1, 202)), "status": "selected"},
        {"status": "selected"},
    ):
        assert client.post(url, json=body, headers=admin_headers).status_code == 422, body
    # an id from a different listing / unknown id -> 404 and nothing moved
    r = move(client, admin_headers, other["id"], ids, "selected")
    assert r.status_code == 404
    assert move(client, admin_headers, listing["id"], ids + [99999], "selected").status_code == 404
    assert move(client, admin_headers, 99999, ids, "selected").status_code == 404
    with db() as session:
        assert {a.status for a in session.scalars(select(Application))} == {"applied"}
    assert audit_rows("application.status") == []


def test_cannot_move_a_withdrawn_application(client, admin_headers, trainer_factory, open_listing):
    _, tclient, _ = trainer_factory("ada@example.test")
    listing = open_listing()
    app_id = apply_to(tclient, listing["id"]).json()["data"]["application"]["id"]
    tclient.post(f"/api/me/applications/{app_id}/withdraw")
    r = move(client, admin_headers, listing["id"], [app_id], "shortlisted")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "application_withdrawn"
    assert outbox_rows("application.status_changed") == []


def test_duplicate_ids_in_request_are_collapsed(client, admin_headers, trainer_factory, open_listing):
    listing = open_listing()
    ids = seed_applicants(trainer_factory, listing["id"], 1)
    r = move(client, admin_headers, listing["id"], ids + ids, "selected")
    assert r.json()["data"]["changed"] == ids
    assert len(outbox_rows("application.status_changed")) == 1


def test_csv_export_columns_escaping_and_withdrawn(client, admin_headers, trainer_factory, open_listing):
    import csv
    import io

    listing = open_listing()
    _, tc, _ = trainer_factory("ada@example.test")
    apply_to(tc, listing["id"], "=HYPERLINK(\"http://evil\")")
    _, t2, _ = trainer_factory("bob@example.test")
    app2 = apply_to(t2, listing["id"], "plain, with comma").json()["data"]["application"]["id"]
    t2.post(f"/api/me/applications/{app2}/withdraw")
    r = client.get(f"/api/admin/opportunities/{listing['id']}/applications.csv", headers=admin_headers)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"] and listing["slug"] in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert [x["email"] for x in rows] == ["ada@example.test", "bob@example.test"]
    assert rows[0]["note"].startswith("'=")  # formula neutralised
    assert rows[1]["status"] == "withdrawn" and rows[1]["note"] == "plain, with comma"
    assert client.get("/api/admin/opportunities/99999/applications.csv", headers=admin_headers).status_code == 404


def test_csv_empty_pipeline_is_header_only(client, admin_headers, open_listing):
    listing = open_listing()
    r = client.get(f"/api/admin/opportunities/{listing['id']}/applications.csv", headers=admin_headers)
    assert len(r.text.strip().splitlines()) == 1


def test_bulk_status_schedules_drain_only_when_emails_queued(
    client, admin_headers, trainer_factory, open_listing, monkeypatch
):
    from src.workshop0.email import sender

    calls = []
    monkeypatch.setattr(sender, "schedule_drain", lambda bg: calls.append(1))
    listing = open_listing()
    ids = seed_applicants(trainer_factory, listing["id"], 2)  # 2 apply() calls also schedule
    base = len(calls)
    move(client, admin_headers, listing["id"], ids, "selected", notify=False)
    assert len(calls) == base
    move(client, admin_headers, listing["id"], ids, "shortlisted")
    assert len(calls) == base + 1
