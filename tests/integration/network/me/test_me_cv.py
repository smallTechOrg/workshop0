"""POST /api/me/cv, POST /api/me/cv/text, GET /api/me/cv/draft, GET /api/me/cv/file.

Upload mechanics (types, sizes, replacement, blobs, download) run with network AI disabled
through the sanctioned `network_ai_disabled` switch, so they assert the `skipped` path and
spend nothing; the real-Anthropic drafting runs live in test_me_drafter.py."""

from __future__ import annotations

import hashlib
import io
import zipfile

import pytest
from me_helpers import MULTI_LINE_CV, blob_files, genai_pdf, image_only_pdf, poll_draft, profile_body
from sqlalchemy import func, select

from src.workshop0.api import network_me
from src.workshop0.db.models import AiUsage, CvDocument, FacilitatorAction
from src.workshop0.db.session import create_db_session


def _error(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    detail = response.json()["detail"]
    assert detail["code"] == code, detail
    return detail


def _upload(client, data: bytes, filename: str, content_type: str = "application/pdf"):
    return client.post("/api/me/cv", files={"file": (filename, data, content_type)})


def _cv_rows() -> list[CvDocument]:
    with create_db_session() as session:
        return list(session.scalars(select(CvDocument)))


@pytest.fixture
def ai_off(network_ai_disabled):
    network_ai_disabled("key")


# --------------------------------------------------------------------------- happy paths


def test_pdf_upload_stores_blob_row_and_skips_draft_when_keyless(trainer, ai_off, blob_root):
    user, client = trainer
    data = genai_pdf().read_bytes()
    response = _upload(client, data, "genai_trainer.pdf")
    assert response.status_code == 200, response.text
    cv = response.json()["data"]["cv"]
    assert set(cv) == {"id", "source", "original_filename", "draft_status"}
    assert cv["source"] == "pdf" and cv["original_filename"] == "genai_trainer.pdf"
    assert cv["draft_status"] in ("pending", "skipped")

    [row] = _cv_rows()
    assert row.user_id == user.id and row.source == "pdf"
    assert row.sha256 == hashlib.sha256(data).hexdigest() and row.size_bytes == len(data)
    assert row.content_type == "application/pdf"
    assert row.storage_key.startswith(f"cv/{user.id}/") and row.storage_key.endswith(".pdf")
    assert len(row.text_extract) >= 200
    [blob] = blob_files(blob_root)
    assert blob.read_bytes() == data

    draft = poll_draft(client)
    assert draft == {"draft_status": "skipped", "draft": None, "autofilled_fields": []}
    with create_db_session() as session:
        assert session.scalar(select(func.count()).select_from(AiUsage)) == 0
        audit = session.scalar(select(FacilitatorAction).where(FacilitatorAction.action == "cv.upload"))
        assert audit.actor == "user" and (audit.subject_type, audit.subject_id) == ("user", user.id)
        assert "text_extract" not in audit.detail_json


def test_pasted_text_is_stored_without_a_blob(trainer, ai_off, blob_root):
    _, client = trainer
    response = client.post("/api/me/cv/text", json={"text": "  " + MULTI_LINE_CV + "  "})
    assert response.status_code == 200, response.text
    cv = response.json()["data"]["cv"]
    assert cv["source"] == "text" and cv["original_filename"] is None
    [row] = _cv_rows()
    assert row.storage_key is None and row.text_extract == MULTI_LINE_CV.strip()
    assert blob_files(blob_root) == []
    assert poll_draft(client)["draft_status"] == "skipped"


def test_keyless_and_workspaceless_still_create_profile(make_user, signed_in_client, network_ai_disabled):
    for which in ("key", "workspace"):
        network_ai_disabled(which)
        user = make_user(f"no-{which}@example.test")
        client = signed_in_client(user)
        assert client.post("/api/me/cv/text", json={"text": MULTI_LINE_CV}).status_code == 200
        assert poll_draft(client)["draft_status"] == "skipped"
        response = client.post("/api/me/profile", json=profile_body())
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["profile"]["cv"]["draft_status"] == "skipped"
        assert data["profile"]["autofilled_fields"] == []
        assert "cv" not in data["completeness"]["missing"]
    with create_db_session() as session:
        assert session.scalar(select(func.count()).select_from(AiUsage)) == 0


# --------------------------------------------------------------------------- replacement + download


def test_new_upload_replaces_row_in_place_and_deletes_old_blob(trainer, ai_off, blob_root):
    _, client = trainer
    first = _upload(client, genai_pdf().read_bytes(), "first.pdf").json()["data"]["cv"]
    [old_blob] = blob_files(blob_root)

    second = _upload(client, genai_pdf().read_bytes(), "second.pdf").json()["data"]["cv"]
    assert second["id"] == first["id"]  # one cv_document per user, id kept (spend stays attributed)
    [new_blob] = blob_files(blob_root)
    assert new_blob != old_blob and not old_blob.exists()
    assert [r.original_filename for r in _cv_rows()] == ["second.pdf"]

    third = client.post("/api/me/cv/text", json={"text": MULTI_LINE_CV}).json()["data"]["cv"]
    assert third["id"] == first["id"] and third["source"] == "text"
    assert blob_files(blob_root) == []
    [row] = _cv_rows()
    assert row.storage_key is None and row.draft_json is None


def test_own_cv_download_returns_the_original_bytes(trainer, ai_off):
    _, client = trainer
    _error(client.get("/api/me/cv/file"), 404, "not_found")
    data = genai_pdf().read_bytes()
    assert _upload(client, data, "Priya CV.pdf").status_code == 200
    response = client.get("/api/me/cv/file")
    assert response.status_code == 200
    assert response.content == data
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment") and "Priya" in disposition

    assert client.post("/api/me/cv/text", json={"text": MULTI_LINE_CV}).status_code == 200
    response = client.get("/api/me/cv/file")
    assert response.status_code == 200
    assert response.text == MULTI_LINE_CV.strip()
    assert response.headers["content-type"].startswith("text/plain")


def test_cv_download_is_own_only(make_user, signed_in_client, ai_off):
    owner = signed_in_client(make_user("owner@example.test"))
    other = signed_in_client(make_user("other@example.test"))
    assert _upload(owner, genai_pdf().read_bytes(), "cv.pdf").status_code == 200
    _error(other.get("/api/me/cv/file"), 404, "not_found")
    _error(other.get("/api/me/cv/draft"), 404, "not_found")


# --------------------------------------------------------------------------- edge + error paths


def test_image_only_pdf_is_cv_unreadable(trainer, blob_root):
    _, client = trainer
    detail = _error(_upload(client, image_only_pdf().read_bytes(), "scan.pdf"), 422, "cv_unreadable")
    assert "paste" in detail["message"].lower()
    assert _cv_rows() == [] and blob_files(blob_root) == []


def _zip(name: str = "hello.txt") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, "not a word document")
    return buffer.getvalue()


@pytest.mark.parametrize(
    "data, filename, content_type",
    [
        (b"", "empty.pdf", "application/pdf"),
        (b"just some text pretending to be a pdf", "cv.pdf", "application/pdf"),
        (b"\x89PNG\r\n\x1a\n" + b"0" * 100, "cv.png", "image/png"),
        (_zip(), "archive.zip", "application/zip"),
        (b"{\\rtf1 hello}", "cv.doc", "application/msword"),
    ],
    ids=["empty", "fake-pdf", "png", "zip", "rtf-doc"],
)
def test_non_pdf_docx_is_unsupported_file(trainer, data, filename, content_type, blob_root):
    _, client = trainer
    _error(_upload(client, data, filename, content_type), 415, "unsupported_file")
    assert _cv_rows() == [] and blob_files(blob_root) == []


def test_over_5mb_is_file_too_large_and_exactly_5mb_is_read(trainer, blob_root):
    _, client = trainer
    limit = 5 * 1024 * 1024
    _error(_upload(client, b"%PDF-1.4\n" + b"0" * limit, "big.pdf"), 413, "file_too_large")
    # exactly at the limit passes the size gate (and then fails extraction: no text)
    _error(_upload(client, b"%PDF-1.4\n" + b"0" * (limit - 9), "edge.pdf"), 422, "cv_unreadable")
    assert _cv_rows() == [] and blob_files(blob_root) == []


def test_missing_file_field_is_validation_error(trainer):
    _, client = trainer
    _error(client.post("/api/me/cv", data={"nope": "x"}), 422, "validation_error")


@pytest.mark.parametrize(
    "body",
    [{}, {"text": None}, {"text": 123}, {"text": "x" * 199}, {"text": " " * 300}, {"text": "x" * 30001}],
    ids=["absent", "null", "number", "199-chars", "whitespace", "30001-chars"],
)
def test_pasted_text_bounds_are_validation_errors(trainer, body):
    _, client = trainer
    detail = _error(client.post("/api/me/cv/text", json=body), 422, "validation_error")
    assert detail["message"].startswith("text")
    assert _cv_rows() == []


def test_pasted_text_boundaries_200_and_30000_are_accepted(trainer, ai_off):
    _, client = trainer
    assert client.post("/api/me/cv/text", json={"text": "a" * 200}).status_code == 200
    assert client.post("/api/me/cv/text", json={"text": "b" * 30000}).status_code == 200


def test_draft_before_any_cv_is_not_found(trainer):
    _, client = trainer
    _error(client.get("/api/me/cv/draft"), 404, "not_found")


# --------------------------------------------------------------------------- background task safety


def test_drafter_crash_marks_failed_not_stuck_pending(trainer, monkeypatch):
    from src.workshop0.ai import profile_draft

    def boom(_cv_id: int) -> None:
        raise RuntimeError("drafter bug")

    monkeypatch.setattr(profile_draft, "run_profile_draft", boom)
    _, client = trainer
    assert client.post("/api/me/cv/text", json={"text": MULTI_LINE_CV}).status_code == 200
    assert poll_draft(client, timeout_s=5)["draft_status"] == "failed"


def test_global_drafting_budget_skips_drafting_but_keeps_the_cv(make_user, signed_in_client, monkeypatch):
    from src.workshop0.ai import profile_draft

    ran: list[int] = []
    monkeypatch.setattr(profile_draft, "run_profile_draft", ran.append)
    monkeypatch.setattr(network_me, "DRAFT_LIMIT", 2)
    for i in range(3):
        client = signed_in_client(make_user(f"budget{i}@example.test"))
        cv = client.post("/api/me/cv/text", json={"text": MULTI_LINE_CV}).json()["data"]["cv"]
        expected = "pending" if i < 2 else "skipped"
        assert cv["draft_status"] == expected
    assert len(ran) == 2
    assert len(_cv_rows()) == 3
