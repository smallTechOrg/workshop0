"""Every /api/me mutation without `X-Requested-With: workshop0` → 403 `csrf_failed`, with no
side effect; GETs need no header."""

from __future__ import annotations

import pytest
from me_helpers import MULTI_LINE_CV, profile_body
from sqlalchemy import func, select

from src.workshop0.db.models import AppUser, CvDocument, RateLimitHit, TrainerProfile
from src.workshop0.db.session import create_db_session

MUTATIONS = [
    ("POST", "/api/me/cv", {"files": {"file": ("cv.pdf", b"%PDF-1.4 tiny", "application/pdf")}}),
    ("POST", "/api/me/cv/text", {"json": {"text": MULTI_LINE_CV}}),
    ("POST", "/api/me/profile", {"json": profile_body()}),
    ("PATCH", "/api/me/profile", {"json": {"headline": "Changed headline"}}),
    ("DELETE", "/api/me", {"json": {"confirm_email": "csrf@example.test"}}),
]


@pytest.mark.parametrize("method, path, kwargs", MUTATIONS, ids=[f"{m} {p}" for m, p, _ in MUTATIONS])
@pytest.mark.parametrize("header", [None, "XMLHttpRequest"], ids=["missing", "wrong-value"])
def test_mutation_without_csrf_header_is_refused(make_user, signed_in_client, method, path, kwargs, header):
    user = make_user("csrf@example.test")
    trusted = signed_in_client(user)
    assert trusted.post("/api/me/profile", json=profile_body(headline="Original headline")).status_code == 200

    client = signed_in_client(user, csrf=False)
    headers = {"X-Requested-With": header} if header else {}
    response = client.request(method, path, headers=headers, **kwargs)
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "csrf_failed"

    with create_db_session() as session:
        assert session.scalar(select(func.count()).select_from(AppUser)) == 1
        assert session.scalar(select(TrainerProfile.headline)) == "Original headline"
        assert session.scalar(select(func.count()).select_from(CvDocument)) == 0
        assert session.scalar(select(func.count()).select_from(RateLimitHit)) == 0  # refused before limiting


def test_reads_need_no_csrf_header(make_user, signed_in_client):
    user = make_user("reader@example.test")
    assert signed_in_client(user).post("/api/me/profile", json=profile_body()).status_code == 200
    client = signed_in_client(user, csrf=False)
    assert client.get("/api/me/profile").status_code == 200
    assert client.get("/api/me/cv/draft").json()["detail"]["code"] == "not_found"
