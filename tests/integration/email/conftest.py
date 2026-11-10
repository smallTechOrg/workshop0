"""Email tests: SMTP is blanked for every test by the root conftest (`.env` may hold real
credentials); tests opt in via `smtp_env` (fake sink)."""

import pytest


@pytest.fixture(autouse=True)
def _email_base_url(monkeypatch):
    monkeypatch.setenv("WORKSHOP0_BASE_URL", "http://base.test")
    import src.workshop0.config.settings as settings_module

    settings_module._settings = None
    yield
    settings_module._settings = None
