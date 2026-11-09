"""C13 Admin trainer pool — trainer detail (+ ai_cost_usd), CV download + `cv.download`
audit (local bytes + Content-Disposition; GCS signed-URL redirect), verify / unverify,
notes, tags, invites, ai-spend, and admin access via the key and via an admin session
(PostgreSQL)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select, text

from tests.conftest import NETWORK_HEADERS
from tests.integration.network.admin.pool_seed import CV_TEXT_SENTINEL, POOL_TAG, seed_cv, seed_profile

BASE = "/api/admin/network"
PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n" + bytes(range(256))


def _audit(action: str | None = None, subject_id: int | None = None) -> list[dict]:
    from src.workshop0.db.models import FacilitatorAction
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        stmt = select(FacilitatorAction).order_by(FacilitatorAction.id)
        if action:
            stmt = stmt.where(FacilitatorAction.action == action)
        if subject_id is not None:
            stmt = stmt.where(FacilitatorAction.subject_id == subject_id)
        return [
            {
                "action": r.action,
                "actor": r.actor,
                "workshop_id": r.workshop_id,
                "subject_type": r.subject_type,
                "subject_id": r.subject_id,
                "detail": json.loads(r.detail_json),
            }
            for r in session.scalars(stmt)
        ]


def _scalar(sql: str, **params):
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        return session.execute(text(sql), params).scalar_one()


@pytest.fixture
def trainer():
    """One trainer with two topics and a tag; returns its ids."""
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        profile = seed_profile(
            session,
            email="Asha@Example.test",
            display_name="Asha Rao",
            headline="GenAI trainer · ex-Flipkart",
            bio_md="Ten years teaching Python.",
            topics={"python": "expert", "generative-ai": "advanced"},
            tags=["mentor"],
            rate=(8000, 15000, "INR", "course"),
            city="Bengaluru",
        )
        return {"id": profile.id, "user_id": profile.user_id}


# --------------------------------------------------------------------------- detail


def test_trainer_detail_is_the_full_admin_view(client, admin_headers, trainer):
    response = client.get(f"{BASE}/trainers/{trainer['id']}", headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert set(data) == {"trainer", "notes", "tags", "cv", "ai_cost_usd", "activity"}
    t = data["trainer"]
    assert t["id"] == trainer["id"] and t["email"] == "asha@example.test"
    assert t["display_name"] == "Asha Rao" and t["bio_md"] == "Ten years teaching Python."
    assert t["rate"] == {"min": 8000, "max": 15000, "currency": "INR", "unit": "course", "pro_bono": False}
    assert t["rate_unit"] == "course"
    assert [x["slug"] for x in t["topics"]] == ["python", "generative-ai"]
    assert t["past_work"] and t["availability"] == {"mon": ["morning"]}
    assert t["available_from"] == "2026-12-01" and t["consent_version"] == "2026-11"
    assert set(t["completeness"]) == {"pct", "missing"} and t["completeness"]["pct"] == t["completeness_pct"]
    assert data["tags"] == ["mentor"] and data["notes"] == [] and data["activity"] == []
    assert data["cv"] is None and data["ai_cost_usd"] == 0.0


@pytest.mark.parametrize("raw", ["999999", "abc", "0", "-1", "1.5"])
def test_unknown_trainer_is_not_found_everywhere(client, admin_headers, raw):
    for method, path, body in (
        ("get", f"{BASE}/trainers/{raw}", None),
        ("get", f"{BASE}/trainers/{raw}/cv", None),
        ("post", f"{BASE}/trainers/{raw}/verify", None),
        ("post", f"{BASE}/trainers/{raw}/notes", {"body": "hello"}),
        ("put", f"{BASE}/trainers/{raw}/tags", {"tags": ["x"]}),
    ):
        kwargs = {"json": body} if body is not None else {}
        response = getattr(client, method)(path, headers=admin_headers, **kwargs)
        assert response.status_code == 404, (method, path, response.text)
        assert response.json()["detail"]["code"] == "not_found"
    assert _audit() == []


def test_trainer_ai_cost_and_network_spend_equal_the_seeded_sums(client, admin_headers, spend_seed):
    detail = client.get(f"{BASE}/trainers/{spend_seed.trainer_profile_id}", headers=admin_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["ai_cost_usd"] == pytest.approx(spend_seed.trainer_cost, abs=1e-9)
    assert detail.json()["data"]["ai_cost_usd"] == pytest.approx(0.013, abs=1e-9)

    response = client.get(f"{BASE}/ai-spend", headers=admin_headers)
    assert response.status_code == 200, response.text
    spend = response.json()["data"]
    assert spend["total_cost_usd"] == pytest.approx(spend_seed.total_cost, abs=1e-9)
    assert spend["total_cost_usd"] == pytest.approx(0.038, abs=1e-9)  # help-desk 6.25 excluded
    assert spend["call_count"] == spend_seed.call_count == 4
    assert spend["prompt_tokens"] == spend_seed.prompt_tokens
    assert spend["completion_tokens"] == spend_seed.completion_tokens
    got = {p["purpose"]: (p["cost_usd"], p["count"]) for p in spend["by_purpose"]}
    assert set(got) == set(spend_seed.by_purpose) == {"profile_draft", "shortlist_rank"}
    for purpose, (cost, count) in spend_seed.by_purpose.items():
        assert got[purpose][0] == pytest.approx(cost, abs=1e-9) and got[purpose][1] == count
    # the help-desk rows really are in the table (so the exclusion is meaningful)
    assert _scalar("SELECT count(*) FROM ai_usage WHERE workshop_id IS NOT NULL") == 2


def test_ai_spend_is_zero_without_network_rows(client, admin_headers):
    response = client.get(f"{BASE}/ai-spend", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["data"] == {
        "total_cost_usd": 0.0, "call_count": 0, "prompt_tokens": 0, "completion_tokens": 0,
        "by_purpose": [],
    }


# --------------------------------------------------------------------------- CV download


def test_cv_download_local_returns_original_bytes_and_audits(client, admin_headers, trainer, blob_root):
    from src.workshop0.db.session import create_db_session
    from src.workshop0.storage import blobstore

    key = f"cv/{trainer['user_id']}/0b5e0a2c.pdf"
    blobstore.get_blobstore().put(key, PDF_BYTES, "application/pdf")
    assert (blob_root / key).is_file(), "the test must write under the per-test root"
    with create_db_session() as session:
        cv = seed_cv(session, trainer["user_id"], storage_key=key, original_filename="Asha Rao CV.pdf",
                     size_bytes=len(PDF_BYTES))
        cv_id = cv.id

    response = client.get(f"{BASE}/trainers/{trainer['id']}/cv", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.content == PDF_BYTES
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;") and "Asha Rao CV.pdf" in disposition.replace("%20", " ")
    assert response.headers["content-type"].startswith("application/pdf")
    rows = _audit("cv.download")
    assert len(rows) == 1
    assert rows[0]["actor"] == "admin" and rows[0]["workshop_id"] is None
    assert rows[0]["subject_type"] == "trainer" and rows[0]["subject_id"] == trainer["id"]
    assert rows[0]["detail"]["by"] == "admin-key" and rows[0]["detail"]["cv_id"] == cv_id

    detail = client.get(f"{BASE}/trainers/{trainer['id']}", headers=admin_headers).json()["data"]
    assert detail["cv"]["id"] == cv_id and detail["cv"]["has_file"] is True
    assert detail["cv"]["original_filename"] == "Asha Rao CV.pdf"
    assert [a["action"] for a in detail["activity"]] == ["cv.download"]
    assert CV_TEXT_SENTINEL not in json.dumps(detail), "detail carries CV meta, never CV text"


def test_cv_download_gcs_backend_redirects_to_the_signed_url_and_audits(
    client, admin_headers, trainer, monkeypatch
):
    from src.workshop0.db.session import create_db_session
    from src.workshop0.storage import blobstore

    signed = "https://storage.googleapis.com/bucket/cv/x.pdf?X-Goog-Signature=abc"
    calls: list[tuple[str, str]] = []

    class FakeGcs:
        def download_response(self, key: str, filename: str):
            calls.append((key, filename))
            return RedirectResponse(signed, status_code=307)

    monkeypatch.setattr(blobstore, "get_blobstore", lambda: FakeGcs())
    with create_db_session() as session:
        seed_cv(session, trainer["user_id"], storage_key=f"cv/{trainer['user_id']}/a.pdf",
                original_filename="asha.pdf")
    response = client.get(
        f"{BASE}/trainers/{trainer['id']}/cv", headers=admin_headers, follow_redirects=False
    )
    assert response.status_code == 307
    assert response.headers["location"] == signed
    assert calls == [(f"cv/{trainer['user_id']}/a.pdf", "asha.pdf")]
    assert len(_audit("cv.download")) == 1


def test_cv_download_of_pasted_text_is_a_txt_attachment(client, admin_headers, trainer):
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        seed_cv(session, trainer["user_id"], storage_key=None, source="text",
                original_filename=None, text_extract="Pasted LinkedIn text — Asha")
    response = client.get(f"{BASE}/trainers/{trainer['id']}/cv", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.text == "Pasted LinkedIn text — Asha"
    assert response.headers["content-type"].startswith("text/plain")
    assert f'filename="cv-{trainer["id"]}.txt"' in response.headers["content-disposition"]
    assert len(_audit("cv.download")) == 1


def test_cv_download_without_cv_or_with_missing_blob_is_404_and_not_audited(
    client, admin_headers, trainer, blob_root
):
    from src.workshop0.db.session import create_db_session

    response = client.get(f"{BASE}/trainers/{trainer['id']}/cv", headers=admin_headers)
    assert response.status_code == 404 and response.json()["detail"]["code"] == "not_found"
    with create_db_session() as session:
        seed_cv(session, trainer["user_id"], storage_key=f"cv/{trainer['user_id']}/gone.pdf")
    response = client.get(f"{BASE}/trainers/{trainer['id']}/cv", headers=admin_headers)
    assert response.status_code == 404 and response.json()["detail"]["code"] == "not_found"
    assert _audit("cv.download") == []


# --------------------------------------------------------------------------- verify / notes / tags


def test_verify_then_unverify_sets_badge_and_audits(client, admin_headers, trainer):
    response = client.post(f"{BASE}/trainers/{trainer['id']}/verify", headers=admin_headers)
    assert response.status_code == 200, response.text
    t = response.json()["data"]["trainer"]
    assert t["verified"] is True and t["verified_by"] == "admin-key" and t["verified_at"]
    listed = client.get(f"{BASE}/trainers", params={"verified": "true"}, headers=admin_headers)
    assert [r["id"] for r in listed.json()["data"]["trainers"]] == [trainer["id"]]

    response = client.post(f"{BASE}/trainers/{trainer['id']}/unverify", headers=admin_headers)
    assert response.status_code == 200, response.text
    t = response.json()["data"]["trainer"]
    assert t["verified"] is False and t["verified_by"] is None and t["verified_at"] is None
    assert [a["action"] for a in response.json()["data"]["activity"]] == ["trainer.unverify", "trainer.verify"]
    rows = _audit(subject_id=trainer["id"])
    assert [r["action"] for r in rows] == ["trainer.verify", "trainer.unverify"]
    assert all(r["subject_type"] == "trainer" and r["detail"]["by"] == "admin-key" for r in rows)
    assert _scalar("SELECT verified FROM trainer_profile WHERE id = :id", id=trainer["id"]) is False


def test_notes_append_with_author_and_audit(client, admin_headers, trainer):
    first = client.post(f"{BASE}/trainers/{trainer['id']}/notes", json={"body": "  Great at evals.  "},
                        headers=admin_headers)
    assert first.status_code == 200, first.text
    assert first.json()["data"]["note"]["body"] == "Great at evals."
    assert first.json()["data"]["note"]["author"] == "admin-key"
    second = client.post(f"{BASE}/trainers/{trainer['id']}/notes", json={"body": "Booked for Dec."},
                         headers=admin_headers)
    notes = second.json()["data"]["notes"]
    assert [n["body"] for n in notes] == ["Booked for Dec.", "Great at evals."]  # newest first
    detail = client.get(f"{BASE}/trainers/{trainer['id']}", headers=admin_headers).json()["data"]
    assert [n["body"] for n in detail["notes"]] == ["Booked for Dec.", "Great at evals."]
    assert [r["action"] for r in _audit("trainer.note")] == ["trainer.note", "trainer.note"]
    assert _scalar("SELECT count(*) FROM admin_note WHERE profile_id = :id", id=trainer["id"]) == 2


@pytest.mark.parametrize("body", [{"body": "   "}, {"body": "x" * 4001}, {}, {"body": None}])
def test_invalid_note_is_rejected_without_writes(client, admin_headers, trainer, body):
    response = client.post(f"{BASE}/trainers/{trainer['id']}/notes", json=body, headers=admin_headers)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_error"
    assert response.json()["detail"]["message"].startswith("body")
    assert _scalar("SELECT count(*) FROM admin_note") == 0 and _audit() == []


def test_tags_replace_the_set_normalise_and_audit(client, admin_headers, trainer):
    response = client.put(
        f"{BASE}/trainers/{trainer['id']}/tags",
        json={"tags": ["  Bengaluru ", "genai  core", "bengaluru", ""]},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["tags"] == ["bengaluru", "genai core"]
    rows = _audit("trainer.tag")
    assert rows[-1]["detail"]["added"] == ["bengaluru", "genai core"]
    assert rows[-1]["detail"]["removed"] == ["mentor"]
    listed = client.get(f"{BASE}/trainers", params={"tag": POOL_TAG}, headers=admin_headers).json()["data"]
    assert [r["id"] for r in listed["trainers"]] == [trainer["id"]]
    assert listed["trainers"][0]["tags"] == ["bengaluru", "genai core"]
    # empty list clears every tag
    cleared = client.put(f"{BASE}/trainers/{trainer['id']}/tags", json={"tags": []}, headers=admin_headers)
    assert cleared.json()["data"]["tags"] == []
    assert _scalar("SELECT count(*) FROM trainer_tag") == 0


@pytest.mark.parametrize(
    "tags", [["-leading"], ["has_underscore"], ["x" * 41], [f"t{i}" for i in range(21)], "notalist"]
)
def test_invalid_tags_are_rejected_without_writes(client, admin_headers, trainer, tags):
    response = client.put(f"{BASE}/trainers/{trainer['id']}/tags", json={"tags": tags}, headers=admin_headers)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_error"
    assert _scalar("SELECT count(*) FROM trainer_tag") == 1  # the original "mentor" survives
    assert _audit() == []


# --------------------------------------------------------------------------- invites


def test_create_and_list_invites(client, admin_headers):
    response = client.post(f"{BASE}/invites", json={"email": " Invitee@Example.TEST ", "name": " Ravi "},
                           headers=admin_headers)
    assert response.status_code == 200, response.text
    invite = response.json()["data"]["invite"]
    token = _scalar("SELECT token FROM network_invite WHERE id = :id", id=invite["id"])
    assert len(token) == 43
    assert invite["url"] == f"http://testserver/invite/{token}"
    assert invite["email"] == "invitee@example.test" and invite["name"] == "Ravi"
    assert invite["accepted_at"] is None and invite["status"] == "pending"
    expires = datetime.strptime(invite["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert abs(expires - (datetime.now(timezone.utc) + timedelta(days=14))) < timedelta(minutes=1)
    rows = _audit("invite.create")
    assert len(rows) == 1 and rows[0]["subject_type"] == "invite" and rows[0]["subject_id"] == invite["id"]
    assert rows[0]["detail"]["by"] == "admin-key"

    second = client.post(f"{BASE}/invites", json={"email": "other@example.test"}, headers=admin_headers)
    second_id = second.json()["data"]["invite"]["id"]
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        session.execute(
            text("UPDATE network_invite SET expires_at = :e WHERE id = :id"),
            {"e": datetime.now(timezone.utc) - timedelta(seconds=1), "id": invite["id"]},
        )
    listed = client.get(f"{BASE}/invites", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    data = listed.json()["data"]
    assert data["total"] == 2 and data["total_pages"] == 1
    statuses = {i["id"]: i["status"] for i in data["invites"]}
    assert statuses == {invite["id"]: "expired", second_id: "pending"}
    assert data["invites"][0]["id"] == second_id  # newest first


def test_invite_redirect_route_lands_on_onboarding(client, admin_headers):
    invite = client.post(f"{BASE}/invites", json={"email": "x@example.test"}, headers=admin_headers)
    path = invite.json()["data"]["invite"]["url"].removeprefix("http://testserver")
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].startswith("/app/network/join/?invite=")


@pytest.mark.parametrize("body", [{"email": "not-an-email"}, {"email": ""}, {}, {"email": "a@b.c", "name": "n" * 121}])
def test_invalid_invite_is_rejected_without_writes(client, admin_headers, body):
    response = client.post(f"{BASE}/invites", json=body, headers=admin_headers)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_error"
    assert _scalar("SELECT count(*) FROM network_invite") == 0


# --------------------------------------------------------------------------- admin access


ENDPOINTS = [
    ("get", f"{BASE}/trainers", None),
    ("get", f"{BASE}/trainers.csv", None),
    ("get", f"{BASE}/trainers/1", None),
    ("get", f"{BASE}/trainers/1/cv", None),
    ("post", f"{BASE}/trainers/1/verify", None),
    ("post", f"{BASE}/trainers/1/unverify", None),
    ("post", f"{BASE}/trainers/1/notes", {"body": "x"}),
    ("put", f"{BASE}/trainers/1/tags", {"tags": ["x"]}),
    ("get", f"{BASE}/invites", None),
    ("post", f"{BASE}/invites", {"email": "a@example.test"}),
    ("get", f"{BASE}/ai-spend", None),
]


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
@pytest.mark.parametrize("key", [None, "wrong-key"])
def test_every_pool_endpoint_requires_admin(client, trainer, method, path, body, key):
    headers = {"X-Admin-Key": key} if key else {}
    kwargs = {"json": body} if body is not None else {}
    response = getattr(client, method)(path, headers=headers, **kwargs)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_admin_key"
    assert _audit() == [] and _scalar("SELECT count(*) FROM network_invite") == 0


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_non_admin_session_is_refused(make_user, signed_in_client, trainer, method, path, body):
    user = make_user("plain@example.test")
    kwargs = {"json": body} if body is not None else {}
    response = getattr(signed_in_client(user), method)(path, **kwargs)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "not_admin"
    assert _audit() == []


def test_admin_session_works_without_the_key_and_is_the_audit_actor(
    make_user, signed_in_client, trainer, pool60
):
    admin = make_user("boss@example.test", admin=True)
    browser = signed_in_client(admin)
    assert "X-Admin-Key" not in browser.headers
    listed = browser.get(f"{BASE}/trainers", params={"page_size": 100})
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["total"] == 61
    assert browser.get(f"{BASE}/trainers.csv").status_code == 200
    assert browser.get(f"{BASE}/ai-spend").status_code == 200
    verify = browser.post(f"{BASE}/trainers/{trainer['id']}/verify")
    assert verify.status_code == 200, verify.text
    assert verify.json()["data"]["trainer"]["verified_by"] == "boss@example.test"
    note = browser.post(f"{BASE}/trainers/{trainer['id']}/notes", json={"body": "Met at PyCon"})
    assert note.json()["data"]["note"]["author"] == "boss@example.test"
    invite = browser.post(f"{BASE}/invites", json={"email": "new@example.test"})
    assert invite.status_code == 200, invite.text
    assert {r["detail"]["by"] for r in _audit()} == {"boss@example.test"}
    assert _scalar("SELECT created_by FROM network_invite") == "boss@example.test"


def test_admin_session_mutation_needs_the_csrf_header(make_user, signed_in_client, trainer):
    admin = make_user("boss@example.test", admin=True)
    browser = signed_in_client(admin, csrf=False)
    assert browser.get(f"{BASE}/trainers").status_code == 200  # reads need no header
    response = browser.post(f"{BASE}/trainers/{trainer['id']}/verify")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "csrf_failed"
    assert _audit() == []
    ok = browser.post(f"{BASE}/trainers/{trainer['id']}/verify", headers=NETWORK_HEADERS)
    assert ok.status_code == 200, ok.text


def test_db_state_is_unchanged_by_reads(client, admin_headers, pool60):
    before = _scalar("SELECT count(*) FROM facilitator_action")
    client.get(f"{BASE}/trainers", headers=admin_headers)
    client.get(f"{BASE}/trainers.csv", headers=admin_headers)
    client.get(f"{BASE}/trainers/{pool60.ids[0]}", headers=admin_headers)
    client.get(f"{BASE}/ai-spend", headers=admin_headers)
    assert _scalar("SELECT count(*) FROM facilitator_action") == before
    from src.workshop0.db.models import TrainerProfile
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        assert session.scalar(select(func.count(TrainerProfile.id))) == 60
