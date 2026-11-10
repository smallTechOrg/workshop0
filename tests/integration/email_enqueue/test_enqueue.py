"""network.welcome on profile create (the invite-email endpoint is covered in admin_matching/test_email_invite_api.py)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.workshop0.db.models import EmailOutbox
from src.workshop0.db.session import create_db_session
from src.workshop0.email import sender

BASE = "http://base.test"


@pytest.fixture
def trainer(make_user, signed_in_client):
    user = make_user("asha@example.test")
    return user, signed_in_client(user)


def _outbox() -> list[EmailOutbox]:
    with create_db_session() as s:
        return list(s.scalars(select(EmailOutbox)))


def test_profile_create_enqueues_one_welcome(trainer):
    _, client = trainer
    body = {"headline": "GenAI trainer", "topics": [{"slug": "python", "level": "expert"}], "consent": True}
    assert client.post("/api/me/profile", json=body).status_code == 200
    rows = _outbox()
    assert len(rows) == 1 and rows[0].template == "network.welcome" and rows[0].to_email == "asha@example.test"
    assert f"{BASE}/app/network/applications/" in rows[0].context_json
    sender.drain()
    assert _outbox()[0].status == "recorded"


def test_failed_profile_create_enqueues_nothing(trainer):
    _, client = trainer
    body = {"headline": "x", "topics": [{"slug": "python", "level": "expert"}], "consent": False}
    assert client.post("/api/me/profile", json=body).status_code == 422
    assert _outbox() == []
