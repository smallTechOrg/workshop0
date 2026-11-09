"""Plain helpers for the `/api/me/*` suite (slice S7)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "cv"
MULTI_LINE_CV = (
    "Priya Raman — Senior Data Engineer and Python trainer based in Pune.\n"
    "Ten years building data pipelines with Python, Airflow and Spark on AWS.\n"
    "Has taught twelve corporate Python bootcamps and spoken at PyCon India 2024.\n"
    "Mentors junior engineers on SQL performance tuning and data modelling.\n"
)  # > 200 characters


def profile_body(**overrides) -> dict:
    """A minimal valid ProfileInput + consent (only headline and ≥1 topic are required)."""
    body = {"headline": "GenAI trainer · ex-Flipkart", "topics": [{"slug": "python", "level": "expert"}],
            "consent": True}
    body.update(overrides)
    return body


def full_profile_body(**overrides) -> dict:
    body = {
        "headline": "GenAI trainer · ex-Flipkart",
        "bio_md": "I teach practical LLM engineering to product teams. " * 3,
        "city": "Bengaluru",
        "remote_ok": True,
        "linkedin_url": "https://www.linkedin.com/in/priya-example",
        "github_url": "https://github.com/priya-example",
        "website_url": "https://priya.example.com",
        "topics": [
            {"slug": "python", "level": "expert"},
            {"slug": "generative-ai", "level": "advanced"},
            {"slug": "prompt-engineering", "level": "intermediate"},
        ],
        "past_work": [{"title": "LLM bootcamp", "kind": "workshop", "org": "Acme", "year": 2025}],
        "rate_min": 40000,
        "rate_max": 60000,
        "rate_currency": "INR",
        "rate_unit": "day",
        "pro_bono": False,
        "availability": {"mon": ["morning", "afternoon"], "sat": ["morning"]},
        "available_from": "2026-12-01",
        "blackouts": [{"start": "2026-12-20", "end": "2027-01-02"}],
        "consent": True,
    }
    body.update(overrides)
    return body


def blob_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def fixture_path(*patterns: str) -> Path:
    """First committed CV fixture (slice S4 owns tests/fixtures/cv/) matching a glob pattern."""
    for pattern in patterns:
        matches = sorted(FIXTURES.glob(pattern))
        if matches:
            return matches[0]
    pytest.fail(f"CV fixture missing under {FIXTURES}: tried {patterns}")


def genai_pdf() -> Path:
    return fixture_path("genai_trainer.pdf")


def image_only_pdf() -> Path:
    return fixture_path("*image*.pdf", "*scan*.pdf")


def poll_draft(client, *, timeout_s: float = 60.0) -> dict:
    """Poll GET /api/me/cv/draft the way the onboarding screen does (1.5 s, ≤60 s)."""
    deadline = time.monotonic() + timeout_s
    while True:
        response = client.get("/api/me/cv/draft")
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        if data["draft_status"] != "pending" or time.monotonic() > deadline:
            return data
        time.sleep(1.5)
