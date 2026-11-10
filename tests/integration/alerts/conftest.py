"""Alerts tests write rows directly and never send mail; real SMTP creds from `.env` are blanked."""

import pytest


@pytest.fixture(autouse=True)
def _no_real_smtp(monkeypatch):
    for name in ("HOST", "USER", "PASSWORD", "FROM"):
        monkeypatch.setenv(f"WORKSHOP0_SMTP_{name}", "")
    import src.workshop0.config.settings as settings_module

    settings_module._settings = None
    yield
    settings_module._settings = None


@pytest.fixture(autouse=True)
def _fake_unsubscribe_url(monkeypatch):
    """`services/unsubscribe.py` belongs to slice D1; this slice only needs a deterministic URL."""
    from src.workshop0.services import unsubscribe

    monkeypatch.setattr(unsubscribe, "url", lambda base, uid, kind: f"{base}/api/email/unsubscribe?t=tok-{uid}-{kind}")
