"""The three drafter fixtures (+ the prompt-injection CV) through the REAL endpoint:
upload/paste → poll GET /api/me/cv/draft → draft, against the real Anthropic API with the key
and workspace id from `.env` (agent.md §Testing). Then the draft is reviewed into a profile.

Skips only when ANTHROPIC_API_KEY / ANTHROPIC_WORKSPACE_ID are genuinely absent; the phase
gate asserts both are present first, so a skip can never pass the gate."""

from __future__ import annotations

import re

import pytest
from me_helpers import fixture_path, poll_draft
from sqlalchemy import select

from src.workshop0.ai import pricing
from src.workshop0.config.settings import get_settings
from src.workshop0.db.models import AiUsage, CvDocument, Topic
from src.workshop0.db.session import create_db_session
from src.workshop0.services.cv_text import extract_text

RATE_WORDS = re.compile(r"(₹|\bINR\b|\bUSD\b|\$\s?\d|per (hour|day)|/hr\b|day rate|hourly rate)", re.I)


@pytest.fixture(autouse=True)
def _real_keys():
    settings = get_settings()
    if not (settings.anthropic_api_key and settings.anthropic_workspace_id):
        pytest.skip("ANTHROPIC_API_KEY / ANTHROPIC_WORKSPACE_ID absent — the gate refuses to run without both")


# (fixture globs, how it is sent, the expected slugs — at least two must be drafted)
CASES = [
    pytest.param(("genai_trainer.pdf",), "pdf", {"generative-ai", "python", "prompt-engineering", "agentic-ai",
                                                 "machine-learning"}, id="genai-pdf"),
    pytest.param(("*devops*.docx", "*cloud*.docx", "*.docx"), "docx",
                 {"aws", "docker", "kubernetes", "terraform", "ci-cd", "gcp", "azure", "linux"}, id="devops-docx"),
    pytest.param(("*linkedin*.txt", "*react*.txt"), "text",
                 {"react", "javascript", "typescript", "nextjs", "nodejs"}, id="react-linkedin-text"),
]


def _cv_text(path, kind: str) -> str:
    return path.read_text(encoding="utf-8") if kind == "text" else extract_text(path.read_bytes(), kind)


def _send(client, path, kind: str):
    if kind == "text":
        return client.post("/api/me/cv/text", json={"text": path.read_text(encoding="utf-8")[:30000]})
    content_type = "application/pdf" if kind == "pdf" else (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return client.post("/api/me/cv", files={"file": (path.name, path.read_bytes(), content_type)})


def _printed_links(text: str, host: str) -> set[str]:
    found = re.findall(rf"https://(?:[a-z]+\.)?{re.escape(host)}/[^\s)>\]]+", text, re.I)
    return {u.rstrip(".,;").rstrip("/").lower() for u in found}


def _curated_slugs() -> set[str]:
    with create_db_session() as session:
        return set(session.scalars(select(Topic.slug).where(Topic.active.is_(True))))


@pytest.mark.parametrize("patterns, kind, expected", CASES)
def test_fixture_cv_drafts_through_the_endpoint(trainer, patterns, kind, expected):
    _, client = trainer
    path = fixture_path(*patterns)
    cv_text = _cv_text(path, kind)

    response = _send(client, path, kind)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["cv"]["source"] == kind

    data = poll_draft(client)
    assert data["draft_status"] == "ready", data
    draft = data["draft"]
    slugs = {t["slug"] for t in draft["topics"]}
    assert slugs <= _curated_slugs(), slugs - _curated_slugs()
    assert len(slugs & expected) >= 2, (slugs, expected)
    assert all(t["level"] in ("intermediate", "advanced", "expert") for t in draft["topics"])
    assert draft["headline"].strip() and len(draft["headline"]) <= 160
    assert data["autofilled_fields"] and "headline" in data["autofilled_fields"] and "topics" in data["autofilled_fields"]

    # links equal to those printed in the CV (never invented)
    for key, host in (("linkedin_url", "linkedin.com"), ("github_url", "github.com")):
        printed = _printed_links(cv_text, host)
        value = draft.get(key)
        if value:
            assert value.rstrip("/").lower() in printed, (key, value, printed)
        elif printed:
            pytest.fail(f"{key} printed in the CV ({printed}) but not drafted")
    if not RATE_WORDS.search(cv_text):
        assert draft.get("rate_min") is None and draft.get("rate_max") is None, draft

    with create_db_session() as session:
        cv = session.scalar(select(CvDocument))
        [usage] = session.scalars(select(AiUsage)).all()
        model = get_settings().workshop0_ai_network_model
        assert usage.purpose == "profile_draft" and usage.model == model
        assert usage.workshop_id is None and usage.cv_document_id == cv.id
        assert usage.prompt_tokens > 0 and usage.completion_tokens > 0
        assert usage.cost_usd == pricing.cost_usd(model, usage.prompt_tokens, usage.completion_tokens) > 0

    # review: the person accepts the draft as-is (+ consent) → live profile
    body = {k: v for k, v in draft.items() if v is not None}
    body["consent"] = True
    created = client.post("/api/me/profile", json=body)
    assert created.status_code == 200, created.text
    profile = created.json()["data"]["profile"]
    assert {t["slug"] for t in profile["topics"]} == slugs
    assert "headline" in profile["autofilled_fields"]  # untouched drafted fields stay "please check"
    assert profile["cv"]["draft_status"] == "ready"
    patched = client.patch("/api/me/profile", json={"headline": profile["headline"]})
    assert patched.json()["data"]["profile"]["autofilled_fields"] == []


def test_prompt_injection_cv_stays_on_the_curated_list(trainer):
    _, client = trainer
    path = fixture_path("*inject*", "*injection*")
    kind = {".pdf": "pdf", ".docx": "docx"}.get(path.suffix, "text")
    assert _send(client, path, kind).status_code == 200
    data = poll_draft(client)
    assert data["draft_status"] in ("ready", "failed"), data
    if data["draft_status"] == "ready":
        slugs = {t["slug"] for t in data["draft"]["topics"]}
        assert "hacking" not in slugs and slugs <= _curated_slugs()
