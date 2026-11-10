"""Fixtures for the Phase-12 applications suite (slice B1)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

from tests.conftest import iso


def db():
    from src.workshop0.db.session import create_db_session

    return create_db_session()


@pytest.fixture
def open_listing(client, admin_headers, create_opportunity):
    """Factory: a published (effective-open) listing through the real admin API."""

    def _make(**overrides) -> dict:
        overrides.setdefault("status", "open")
        return create_opportunity(**overrides)

    return _make


@pytest.fixture
def trainer_factory(make_user, signed_in_client):
    """Factory `(email, consent=True, **profile) -> (user, client, profile_id)` via the real API."""
    from tests.integration.network.me.me_helpers import profile_body

    def _make(email: str, **profile):
        user = make_user(email)
        client_ = signed_in_client(user)
        response = client_.post("/api/me/profile", json=profile_body(**profile))
        assert response.status_code == 200, response.text
        with db() as session:
            from src.workshop0.db.models import TrainerProfile

            pid = session.scalar(select(TrainerProfile.id).where(TrainerProfile.user_id == user.id))
        return user, client_, pid

    return _make


def apply_to(client_, opportunity_id: int, note: str | None = None):
    body = {"opportunity_id": opportunity_id}
    if note is not None:
        body["note"] = note
    return client_.post("/api/me/applications", json=body)


def outbox_rows(template: str | None = None) -> list:
    from src.workshop0.db.models import EmailOutbox

    with db() as session:
        stmt = select(EmailOutbox).order_by(EmailOutbox.id)
        if template:
            stmt = stmt.where(EmailOutbox.template == template)
        rows = list(session.scalars(stmt))
        session.expunge_all()
        return rows


def audit_rows(action: str) -> list:
    from src.workshop0.db.models import FacilitatorAction

    with db() as session:
        rows = list(session.scalars(select(FacilitatorAction).where(FacilitatorAction.action == action)))
        session.expunge_all()
        return rows


def ctx(row) -> dict:
    return json.loads(row.context_json)


def make_expired(opportunity_id: int) -> None:
    past = datetime.now(timezone.utc) - timedelta(days=1)
    with db() as session:
        session.execute(
            text("UPDATE opportunity SET deadline = :d WHERE id = :i"), {"d": past, "i": opportunity_id}
        )
        session.commit()
