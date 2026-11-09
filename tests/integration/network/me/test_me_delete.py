"""DELETE /api/me — removes user, profile (+ topics/tags/notes), CV row, blob file and
sessions; writes `account.delete` with only the masked email; clears the cookie."""

from __future__ import annotations

import json
from decimal import Decimal

from me_helpers import blob_files, full_profile_body, genai_pdf
from sqlalchemy import func, select, text

from src.workshop0.db.models import (
    AdminNote,
    AiUsage,
    AppUser,
    AuthSession,
    CvDocument,
    FacilitatorAction,
    TrainerProfile,
    TrainerTag,
    TrainerTopic,
)
from src.workshop0.db.session import create_db_session


def _count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def _seed_trainer(make_user, signed_in_client, network_ai_disabled, email="Delete.Me@Example.test"):
    network_ai_disabled("key")
    user = make_user(email)
    client = signed_in_client(user)
    second_device = signed_in_client(user)
    assert client.post("/api/me/cv", files={"file": ("cv.pdf", genai_pdf().read_bytes(), "application/pdf")}).status_code == 200
    created = client.post("/api/me/profile", json=full_profile_body())
    assert created.status_code == 200, created.text
    profile_id = created.json()["data"]["profile"]["id"]
    with create_db_session() as session:
        cv_id = session.scalar(select(CvDocument.id))
        session.add(TrainerTag(profile_id=profile_id, tag="genai"))
        session.add(AdminNote(profile_id=profile_id, body="Great trainer", author="admin@example.test"))
        session.add(
            AiUsage(
                workshop_id=None, cv_document_id=cv_id, purpose="profile_draft", model="claude-sonnet-5-5",
                prompt_tokens=10, completion_tokens=5, cost_usd=Decimal("0.0001"),
            )
        )
    return user, client, second_device


def test_delete_removes_everything_and_audits_masked_email(
    make_user, signed_in_client, network_ai_disabled, blob_root
):
    user, client, second_device = _seed_trainer(make_user, signed_in_client, network_ai_disabled)
    other = make_user("bystander@example.test")
    bystander = signed_in_client(other)
    assert len(blob_files(blob_root)) == 1

    response = client.request("DELETE", "/api/me", json={"confirm_email": "  DELETE.me@example.TEST "})
    assert response.status_code == 200, response.text
    assert response.json() == {"data": {"deleted": True}, "error": None}
    set_cookie = response.headers.get("set-cookie", "")
    assert "workshop0_session=" in set_cookie and ("Max-Age=0" in set_cookie or "expires=" in set_cookie.lower())

    with create_db_session() as session:
        assert session.get(AppUser, user.id) is None
        assert session.scalar(select(func.count()).select_from(AuthSession).where(AuthSession.user_id == user.id)) == 0
        assert _count(session, TrainerProfile) == 0
        assert _count(session, TrainerTopic) == 0
        assert _count(session, TrainerTag) == 0
        assert _count(session, AdminNote) == 0
        assert _count(session, CvDocument) == 0
        # spend survives, detached from the deleted CV
        [usage] = session.scalars(select(AiUsage)).all()
        assert usage.cv_document_id is None and usage.cost_usd == Decimal("0.0001")
        # the bystander is untouched
        assert session.get(AppUser, other.id) is not None

        [audit] = session.scalars(select(FacilitatorAction).where(FacilitatorAction.action == "account.delete"))
        assert audit.actor == "user" and audit.workshop_id is None
        assert (audit.subject_type, audit.subject_id) == ("user", user.id)
        assert json.loads(audit.detail_json) == {"email": "de***@example.test"}
        # the full address appears in no audit row at all
        rows = session.execute(text("SELECT detail_json FROM facilitator_action")).scalars().all()
        assert not any(user.email in r.lower() for r in rows)
    assert blob_files(blob_root) == []

    # every session of the account is dead, the bystander's lives
    assert second_device.get("/api/me/profile").json()["detail"]["code"] == "not_signed_in"
    assert client.get("/api/me/profile").status_code == 401
    assert bystander.get("/api/me/profile").json()["detail"]["code"] == "not_found"

    # signing up again with the same email starts fresh
    again = signed_in_client(make_user(user.email))
    assert again.get("/api/me/profile").json()["detail"]["code"] == "not_found"


def test_delete_with_wrong_confirmation_changes_nothing(
    make_user, signed_in_client, network_ai_disabled, blob_root
):
    user, client, _ = _seed_trainer(make_user, signed_in_client, network_ai_disabled)
    for body in ({"confirm_email": "someone@else.test"}, {"confirm_email": ""}, {}, {"confirm_email": 5}):
        response = client.request("DELETE", "/api/me", json=body)
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "validation_error"
        assert response.json()["detail"]["message"].startswith("confirm_email")
    with create_db_session() as session:
        assert session.get(AppUser, user.id) is not None
        assert _count(session, TrainerProfile) == 1 and _count(session, CvDocument) == 1
        assert session.scalar(select(FacilitatorAction).where(FacilitatorAction.action == "account.delete")) is None
    assert len(blob_files(blob_root)) == 1
    assert client.get("/api/me/profile").status_code == 200


def test_delete_account_without_profile_or_cv(make_user, signed_in_client):
    user = make_user("bare@example.test")
    client = signed_in_client(user)
    response = client.request("DELETE", "/api/me", json={"confirm_email": user.email})
    assert response.status_code == 200, response.text
    with create_db_session() as session:
        assert session.get(AppUser, user.id) is None
        assert _count(session, AuthSession) == 0
