"""Opportunity/topic admin actions are audited in facilitator_action — exactly one row
per write (actor `admin`, no workshop, subject set), none for a no-op; `activity` is
newest first (PostgreSQL)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from tests.conftest import iso


def _audit_rows() -> list[dict]:
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        return [
            dict(r._mapping)
            for r in session.execute(text(
                "SELECT id, workshop_id, actor, action, detail_json, subject_type, subject_id"
                " FROM facilitator_action ORDER BY id"
            ))
        ]


def _new_rows(before: int) -> list[dict]:
    import json

    rows = _audit_rows()[before:]
    for row in rows:
        row["detail"] = json.loads(row.pop("detail_json"))
    return rows


def test_each_opportunity_write_records_exactly_one_audit_row(client, admin_headers, create_opportunity):
    opp = create_opportunity(["python"])
    rows = _new_rows(0)
    # the fixture's legacy partner_internal_name creates its partner in the same transaction
    assert [r["action"] for r in rows] == ["partner.create", "opportunity.create"]
    assert rows[0]["detail"]["by"] == "admin-key" and rows[0]["subject_type"] == "partner"
    create = rows[1]
    assert (create["actor"], create["workshop_id"], create["action"]) == ("admin", None, "opportunity.create")
    assert (create["subject_type"], create["subject_id"]) == ("opportunity", opp["id"])
    assert create["detail"]["title"] == opp["title"] and create["detail"]["by"] == "admin-key"
    assert create["detail"]["to_status"] == "draft"
    assert {"title", "summary", "topic_ids", "deadline"} <= set(create["detail"]["changed_fields"])
    path = f"/api/admin/opportunities/{opp['id']}"
    future = iso(datetime.now(timezone.utc) + timedelta(days=20))

    steps = [
        ({"summary": "Updated summary", "deadline": future}, "opportunity.update", ["summary", "deadline"], None),
        ({"status": "open"}, "opportunity.publish", [], ("draft", "open")),
        ({"status": "draft", "title": "Back to draft"}, "opportunity.unpublish", ["title"], ("open", "draft")),
        ({"status": "closed"}, "opportunity.close", [], ("draft", "closed")),
        ({"status": "open", "city": None}, "opportunity.publish", [], ("closed", "open")),  # reopen
    ]
    for body, action, changed, transition in steps:
        before = len(_audit_rows())
        response = client.patch(path, json=body, headers=admin_headers)
        assert response.status_code == 200, (body, response.text)
        rows = _new_rows(before)
        assert len(rows) == 1, body
        row = rows[0]
        assert row["action"] == action and row["actor"] == "admin" and row["workshop_id"] is None
        assert (row["subject_type"], row["subject_id"]) == ("opportunity", opp["id"])
        assert row["detail"]["changed_fields"] == changed
        if transition:
            assert (row["detail"]["from_status"], row["detail"]["to_status"]) == transition
        else:
            assert "from_status" not in row["detail"]

    activity = client.get(path, headers=admin_headers).json()["data"]["activity"]
    assert [a["action"] for a in activity] == [
        "opportunity.publish", "opportunity.close", "opportunity.unpublish",
        "opportunity.publish", "opportunity.update", "opportunity.create",
    ]
    assert activity[0]["detail"]["from_status"] == "closed"
    assert set(activity[0]) == {"id", "action", "detail", "created_at"}
    ids = [a["id"] for a in activity]
    assert ids == sorted(ids, reverse=True)


def test_no_op_patch_writes_no_audit_row_and_keeps_updated_at(client, admin_headers, create_opportunity, topic_ids):
    opp = create_opportunity(["python", "go"], status="open")
    before = len(_audit_rows())
    same = {
        "title": opp["title"], "summary": f"  {opp['summary']} ", "status": "open",
        "topic_ids": [topic_ids["go"], topic_ids["python"]], "deadline": opp["deadline"],
        "city": None, "partner_internal_name": opp["partner_internal_name"],
    }
    response = client.patch(f"/api/admin/opportunities/{opp['id']}", json=same, headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["opportunity"]["updated_at"] == opp["updated_at"]
    assert len(_audit_rows()) == before
    assert client.patch(f"/api/admin/opportunities/{opp['id']}", json={}, headers=admin_headers).status_code == 200
    assert len(_audit_rows()) == before


def test_rejected_writes_record_nothing(client, admin_headers, create_opportunity):
    opp = create_opportunity()
    before = len(_audit_rows())
    response = client.patch(
        f"/api/admin/opportunities/{opp['id']}", json={"title": "x"}, headers=admin_headers
    )
    assert response.status_code == 422
    assert len(_audit_rows()) == before


def test_topic_create_and_update_write_topic_rows(client, admin_headers, topic_ids):
    created = client.post(
        "/api/admin/topics", json={"name": "Elixir", "category": "Languages"}, headers=admin_headers
    ).json()["data"]["topic"]
    client.patch(f"/api/admin/topics/{created['id']}", json={"name": "Elixir & Erlang", "active": False},
                 headers=admin_headers)
    client.patch(f"/api/admin/topics/{created['id']}", json={"active": False}, headers=admin_headers)  # no-op
    rows = _new_rows(0)
    assert [r["action"] for r in rows] == ["topic.create", "topic.update"]
    for row in rows:
        assert (row["actor"], row["workshop_id"]) == ("admin", None)
        assert (row["subject_type"], row["subject_id"]) == ("topic", created["id"])
    assert rows[0]["detail"]["slug"] == "elixir"
    assert rows[1]["detail"]["changed_fields"] == ["name", "active"]


def test_workshop_audit_rows_keep_a_null_subject(client, workshop):
    rows = _audit_rows()
    assert rows and all(r["subject_type"] is None and r["subject_id"] is None for r in rows)
    assert rows[0]["workshop_id"] == workshop["id"]
