"""Hook tests: real SMTP creds from `.env` are blanked; `sender.drain` is recorded, never run."""

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
    from src.workshop0.services import unsubscribe

    monkeypatch.setattr(unsubscribe, "url", lambda base, uid, kind: f"{base}/u?t={uid}-{kind}")


@pytest.fixture
def drains(monkeypatch):
    from src.workshop0.email import sender

    calls: list[int] = []
    monkeypatch.setattr(sender, "drain", lambda limit=20: calls.append(limit))
    return calls
