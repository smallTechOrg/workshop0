"""CV upload/paste: 10/h/user — the 11th in the window → 429 `rate_limited` with Retry-After,
counted in the shared DB so the limit holds across two app instances."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from me_helpers import MULTI_LINE_CV
from sqlalchemy import select

from src.workshop0.db.models import CvDocument, RateLimitHit
from src.workshop0.db.session import create_db_session


@pytest.fixture
def no_drafting(monkeypatch):
    """The limiter is the subject here, not the drafter: record instead of calling Anthropic."""
    from src.workshop0.ai import profile_draft

    ran: list[int] = []
    monkeypatch.setattr(profile_draft, "run_profile_draft", ran.append)
    return ran


def _client_for(app, token_client: TestClient) -> TestClient:
    client = TestClient(app)
    client.cookies.update(token_client.cookies)
    client.headers.update({"X-Requested-With": "workshop0"})
    return client


def test_eleventh_cv_in_an_hour_is_429_across_two_instances(
    make_user, signed_in_client, make_app, no_drafting
):
    user = make_user("busy@example.test")
    first = signed_in_client(user)
    second = _client_for(make_app(), first)  # a second app instance, same DB, same session

    for i in range(10):
        client = first if i % 2 == 0 else second
        response = client.post("/api/me/cv/text", json={"text": MULTI_LINE_CV + str(i)})
        assert response.status_code == 200, (i, response.text)

    for client in (second, first):
        blocked = client.post("/api/me/cv/text", json={"text": MULTI_LINE_CV})
        assert blocked.status_code == 429, blocked.text
        assert blocked.json()["detail"]["code"] == "rate_limited"
        retry_after = int(blocked.headers["Retry-After"])
        assert 1 <= retry_after <= 3600
        # uploads share the bucket with pastes
        upload = client.post("/api/me/cv", files={"file": ("cv.pdf", b"%PDF-1.4 x", "application/pdf")})
        assert upload.status_code == 429
        assert upload.json()["detail"]["code"] == "rate_limited"

    with create_db_session() as session:
        [row] = session.scalars(select(CvDocument)).all()
        assert row.text_extract.endswith("9")  # the 10th paste is the stored one
        hits = session.scalars(select(RateLimitHit).where(RateLimitHit.bucket == f"cv:user:{user.id}")).all()
        assert sum(h.count for h in hits) == 14
    assert len(no_drafting) == 10


def test_limit_is_per_user(make_user, signed_in_client, no_drafting):
    busy = signed_in_client(make_user("busy@example.test"))
    for _ in range(10):
        assert busy.post("/api/me/cv/text", json={"text": MULTI_LINE_CV}).status_code == 200
    assert busy.post("/api/me/cv/text", json={"text": MULTI_LINE_CV}).status_code == 429
    calm = signed_in_client(make_user("calm@example.test"))
    assert calm.post("/api/me/cv/text", json={"text": MULTI_LINE_CV}).status_code == 200


def test_previous_window_hits_do_not_count(make_user, signed_in_client, no_drafting):
    """Ten hits in the previous hour's window leave the current window open."""
    from src.workshop0.services.ratelimit import window_start_for

    user = make_user("yesterday@example.test")
    now = datetime.now(timezone.utc)
    previous = window_start_for(now, 3600).timestamp() - 3600
    with create_db_session() as session:
        session.add(
            RateLimitHit(
                bucket=f"cv:user:{user.id}",
                window_start=datetime.fromtimestamp(previous, tz=timezone.utc),
                count=10,
            )
        )
    client = signed_in_client(user)
    assert client.post("/api/me/cv/text", json={"text": MULTI_LINE_CV}).status_code == 200
