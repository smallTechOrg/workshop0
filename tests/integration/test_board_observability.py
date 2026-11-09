"""Board writes emit structured INFO events with ids — never the internal partner name."""

from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from tests.conftest import INTERNAL_NOTE_SENTINEL, INTERNAL_PARTNER_SENTINEL, opportunity_body


def test_publishing_emits_created_and_status_changed_without_internal_names(
    monkeypatch, make_app, admin_headers
):
    import src.workshop0.config.settings as settings_module

    monkeypatch.setenv("WORKSHOP0_LOG_LEVEL", "INFO")  # the suite default (WARNING) filters INFO
    settings_module._settings = None
    client = TestClient(make_app())  # configures logging at INFO; capture after that
    topics = client.get("/api/admin/topics", headers=admin_headers).json()["data"]["topics"]
    body = opportunity_body(
        [topics[0]["id"]],
        partner_internal_name=INTERNAL_PARTNER_SENTINEL,
        internal_notes=INTERNAL_NOTE_SENTINEL,
    )

    with capture_logs() as events:
        opp = client.post("/api/admin/opportunities", json=body, headers=admin_headers).json()["data"]["opportunity"]
        response = client.patch(
            f"/api/admin/opportunities/{opp['id']}", json={"status": "open"}, headers=admin_headers
        )
        assert response.status_code == 200
        client.patch(f"/api/admin/opportunities/{opp['id']}", json={"summary": "Edited"}, headers=admin_headers)
        client.post("/api/admin/topics", json={"name": "Elixir", "category": "Languages"}, headers=admin_headers)

    by_event: dict[str, list[dict]] = {}
    for event in events:
        by_event.setdefault(event["event"], []).append(event)
    created = by_event["opportunity.created"]
    assert len(created) == 1 and created[0]["opportunity_id"] == opp["id"] and created[0]["log_level"] == "info"
    changed = by_event["opportunity.status_changed"]
    assert len(changed) == 1
    assert changed[0]["opportunity_id"] == opp["id"]
    assert (changed[0]["from_status"], changed[0]["to_status"]) == ("draft", "open")
    assert by_event["opportunity.updated"][0]["changed_fields"] == ["summary"]
    assert by_event["topic.created"][0]["slug"] == "elixir"
    for event in events:
        flat = repr(event)
        assert INTERNAL_PARTNER_SENTINEL not in flat and INTERNAL_NOTE_SENTINEL not in flat
