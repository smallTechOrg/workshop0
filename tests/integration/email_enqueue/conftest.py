"""Email tests never touch a real mail server: `.env` may hold real SMTP credentials, so every
test here starts with them blanked (env wins over `.env`); tests opt in via `smtp_env` (fake sink)."""

import pytest


@pytest.fixture(autouse=True)
def _no_real_smtp(monkeypatch):
    for name in ("HOST", "USER", "PASSWORD", "FROM"):
        monkeypatch.setenv(f"WORKSHOP0_SMTP_{name}", "")
    monkeypatch.setenv("WORKSHOP0_BASE_URL", "http://base.test")
    import src.workshop0.config.settings as settings_module

    settings_module._settings = None
    yield
    settings_module._settings = None
