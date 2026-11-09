"""POST/GET/PATCH /api/me/profile — create, consent, validation, invite-verified, patch."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from me_helpers import full_profile_body, profile_body
from sqlalchemy import select

from src.workshop0.db.models import FacilitatorAction, NetworkInvite, TrainerProfile, TrainerTopic
from src.workshop0.db.session import create_db_session


def _error(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    detail = response.json()["detail"]
    assert detail["code"] == code, detail
    return detail


# --------------------------------------------------------------------------- happy path


def test_create_full_profile_round_trips_and_persists(trainer):
    user, client = trainer
    response = client.post("/api/me/profile", json=full_profile_body())
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    profile = payload["profile"]
    assert profile["headline"] == "GenAI trainer · ex-Flipkart"
    assert profile["email"] == user.email
    assert {t["slug"] for t in profile["topics"]} == {"python", "generative-ai", "prompt-engineering"}
    assert {t["slug"]: t["level"] for t in profile["topics"]}["python"] == "expert"
    assert all(t["name"] for t in profile["topics"])
    assert profile["rate_min"] == 40000 and profile["rate_max"] == 60000
    assert profile["rate_currency"] == "INR" and profile["rate_unit"] == "day"
    assert profile["availability"] == {"mon": ["morning", "afternoon"], "sat": ["morning"]}
    assert profile["available_from"] == "2026-12-01"
    assert profile["blackouts"] == [{"start": "2026-12-20", "end": "2027-01-02"}]
    assert profile["past_work"] == [{"title": "LLM bootcamp", "kind": "workshop", "org": "Acme", "year": 2025}]
    assert profile["verified"] is False
    assert profile["consent_version"] == "2026-11" and profile["consent_at"].endswith("Z")
    assert profile["cv"] is None
    # everything but the CV is filled in
    assert payload["completeness"] == {"pct": 90, "missing": ["cv"]}

    with create_db_session() as session:
        row = session.scalar(select(TrainerProfile).where(TrainerProfile.user_id == user.id))
        assert row is not None and row.consent_at is not None
        assert row.city == "Bengaluru" and row.verified is False
        assert len(session.scalars(select(TrainerTopic).where(TrainerTopic.profile_id == row.id)).all()) == 3
        audit = session.scalars(
            select(FacilitatorAction).where(FacilitatorAction.action == "profile.create")
        ).all()
        assert len(audit) == 1
        assert audit[0].actor == "user" and audit[0].workshop_id is None
        assert (audit[0].subject_type, audit[0].subject_id) == ("trainer", row.id)
        assert user.email not in audit[0].detail_json

    again = client.get("/api/me/profile")
    assert again.status_code == 200
    assert again.json()["data"] == payload


def test_minimal_profile_only_needs_headline_and_one_topic(trainer):
    _, client = trainer
    response = client.post("/api/me/profile", json=profile_body())
    assert response.status_code == 200, response.text
    profile = response.json()["data"]["profile"]
    assert profile["bio_md"] == "" and profile["remote_ok"] is True and profile["pro_bono"] is False
    assert profile["linkedin_url"] is None and profile["past_work"] == [] and profile["availability"] == {}


@pytest.mark.parametrize("unit", ["hour", "day", "course", "month"])
def test_rate_unit_accepts_all_four_units(trainer, unit):
    _, client = trainer
    response = client.post(
        "/api/me/profile",
        json=profile_body(rate_min=100, rate_max=200, rate_currency="USD", rate_unit=unit),
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["profile"]["rate_unit"] == unit


# --------------------------------------------------------------------------- error paths


@pytest.mark.parametrize("consent", [None, False, "absent"])
def test_consent_missing_is_validation_error_and_writes_nothing(trainer, consent):
    _, client = trainer
    body = profile_body()
    if consent == "absent":
        body.pop("consent")
    else:
        body["consent"] = consent
    detail = _error(client.post("/api/me/profile", json=body), 422, "validation_error")
    assert detail["message"] == "consent: please agree to continue"
    with create_db_session() as session:
        assert session.scalar(select(TrainerProfile)) is None


def test_second_create_is_profile_exists(trainer):
    _, client = trainer
    assert client.post("/api/me/profile", json=profile_body()).status_code == 200
    _error(client.post("/api/me/profile", json=profile_body(headline="Another one")), 409, "profile_exists")


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"headline": "ab"}, "headline"),
        ({"headline": "x" * 161}, "headline"),
        ({"topics": []}, "topics"),
        ({"topics": [{"slug": "no-such-topic", "level": "expert"}]}, "topics"),
        ({"topics": [{"slug": "python", "level": "guru"}]}, "topics"),
        ({"topics": [{"slug": "python", "level": "expert"}, {"slug": "python", "level": "advanced"}]}, "topics"),
        ({"rate_min": 500, "rate_max": 100}, "rate_min"),
        ({"rate_unit": "week"}, "rate_unit"),
        ({"rate_currency": "EUR"}, "rate_currency"),
        ({"linkedin_url": "https://evil.example/in/x"}, "linkedin_url"),
        ({"linkedin_url": "http://linkedin.com/in/x"}, "linkedin_url"),
        ({"github_url": "https://gitlab.com/x"}, "github_url"),
        ({"availability": {"funday": ["morning"]}}, "availability"),
        ({"availability": {"mon": ["midnight"]}}, "availability"),
        ({"blackouts": [{"start": "2027-01-02", "end": "2026-12-20"}]}, "blackouts"),
        ({"past_work": [{"title": "x", "kind": "workshop", "year": 1900}]}, "past_work"),
        ({"bio_md": "b" * 4001}, "bio_md"),
    ],
)
def test_invalid_profile_input_is_validation_error(trainer, overrides, field):
    _, client = trainer
    detail = _error(client.post("/api/me/profile", json=profile_body(**overrides)), 422, "validation_error")
    assert detail["message"].startswith(field), detail
    with create_db_session() as session:
        assert session.scalar(select(TrainerProfile)) is None


def test_missing_headline_and_topics_are_validation_errors(trainer):
    _, client = trainer
    body = profile_body()
    body.pop("headline")
    _error(client.post("/api/me/profile", json=body), 422, "validation_error")
    body = profile_body()
    body.pop("topics")
    _error(client.post("/api/me/profile", json=body), 422, "validation_error")


def test_signed_out_is_not_signed_in(client):
    for method, path in [("GET", "/api/me/profile"), ("POST", "/api/me/profile"), ("PATCH", "/api/me/profile"),
                         ("GET", "/api/me/cv/draft"), ("GET", "/api/me/cv/file"), ("DELETE", "/api/me")]:
        response = client.request(method, path, json=profile_body(), headers={"X-Requested-With": "workshop0"})
        _error(response, 401, "not_signed_in")


def test_get_profile_without_one_is_not_found(trainer):
    _, client = trainer
    _error(client.get("/api/me/profile"), 404, "not_found")
    _error(client.patch("/api/me/profile", json={"headline": "New headline"}), 404, "not_found")


# --------------------------------------------------------------------------- invite → verified


def _accepted_invite(user_id: int, email: str, *, accepted: bool = True) -> None:
    now = datetime.now(timezone.utc)
    with create_db_session() as session:
        session.add(
            NetworkInvite(
                token="t" * 43 if accepted else "u" * 43,
                email=email,
                name="Invited",
                created_by="admin@example.test",
                expires_at=now + timedelta(days=14),
                accepted_at=now if accepted else None,
                accepted_user_id=user_id if accepted else None,
            )
        )


def test_create_after_accepted_invite_starts_verified(trainer):
    user, client = trainer
    _accepted_invite(user.id, user.email)
    response = client.post("/api/me/profile", json=profile_body())
    assert response.status_code == 200, response.text
    profile = response.json()["data"]["profile"]
    assert profile["verified"] is True and profile["verified_at"].endswith("Z")
    with create_db_session() as session:
        row = session.scalar(select(TrainerProfile))
        assert row.verified is True and row.verified_by == "admin@example.test"


def test_unaccepted_invite_does_not_verify(trainer):
    user, client = trainer
    _accepted_invite(user.id, user.email, accepted=False)
    response = client.post("/api/me/profile", json=profile_body())
    assert response.json()["data"]["profile"]["verified"] is False


# --------------------------------------------------------------------------- patch


def test_patch_is_partial_clears_autofilled_and_audits(trainer):
    user, client = trainer
    assert client.post("/api/me/profile", json=full_profile_body()).status_code == 200
    with create_db_session() as session:
        row = session.scalar(select(TrainerProfile))
        row.autofilled_fields_json = json.dumps(["headline", "topics"])
    assert client.get("/api/me/profile").json()["data"]["profile"]["autofilled_fields"] == ["headline", "topics"]

    response = client.patch(
        "/api/me/profile",
        json={"city": "Pune", "topics": [{"slug": "react", "level": "advanced"}], "rate_unit": "month"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    profile = data["profile"]
    assert profile["city"] == "Pune"
    assert [t["slug"] for t in profile["topics"]] == ["react"]
    assert profile["rate_unit"] == "month"
    assert profile["headline"] == "GenAI trainer · ex-Flipkart"  # untouched
    assert profile["rate_min"] == 40000  # untouched
    assert profile["autofilled_fields"] == []
    assert "topics" in data["completeness"]["missing"]  # 1 topic < 3

    with create_db_session() as session:
        audit = session.scalar(select(FacilitatorAction).where(FacilitatorAction.action == "profile.update"))
        assert json.loads(audit.detail_json) == {"changed_fields": ["city", "rate_unit", "topics"]}
        assert audit.actor == "user"


def test_patch_null_clears_optional_and_rejects_required(trainer):
    _, client = trainer
    assert client.post("/api/me/profile", json=full_profile_body()).status_code == 200
    response = client.patch("/api/me/profile", json={"city": None, "linkedin_url": "", "bio_md": None})
    assert response.status_code == 200, response.text
    profile = response.json()["data"]["profile"]
    assert profile["city"] is None and profile["linkedin_url"] is None and profile["bio_md"] == ""
    _error(client.patch("/api/me/profile", json={"headline": None}), 422, "validation_error")
    _error(client.patch("/api/me/profile", json={"topics": None}), 422, "validation_error")
    # rate_min > stored rate_max is caught against the merged state
    detail = _error(client.patch("/api/me/profile", json={"rate_min": 70000}), 422, "validation_error")
    assert detail["message"].startswith("rate_min")


def test_profiles_are_isolated_between_users(make_user, signed_in_client):
    a = signed_in_client(make_user("a@example.test"))
    b = signed_in_client(make_user("b@example.test"))
    assert a.post("/api/me/profile", json=profile_body(headline="Alice the trainer")).status_code == 200
    _error(b.get("/api/me/profile"), 404, "not_found")
    assert b.post("/api/me/profile", json=profile_body(headline="Bob the trainer")).status_code == 200
    assert a.get("/api/me/profile").json()["data"]["profile"]["headline"] == "Alice the trainer"
    assert b.get("/api/me/profile").json()["data"]["profile"]["headline"] == "Bob the trainer"
