"""Fixtures for the `/api/auth/*` suite (slice S1).

Every test signs in through the REAL OIDC protocol path: the app's `/api/auth/google/start`
→ the in-process issuer `tests/support/fake_oidc.py` (discovery, authorize, token, JWKS, RS256)
→ the app's callback. Nothing on the app side is mocked.
"""

from __future__ import annotations

import secrets

import pytest
from auth_helpers import ADMIN_EMAIL, CLIENT_ID, CLIENT_SECRET

from tests.support.fake_oidc import run_in_thread


@pytest.fixture(scope="session")
def fake_issuer():
    issuer = run_in_thread(port=0)
    yield issuer
    issuer.stop()


@pytest.fixture(autouse=True)
def auth_env(_isolated_env, fake_issuer, monkeypatch):
    """Sign-in enabled against the in-process issuer; one allowlisted admin."""
    import src.workshop0.config.settings as settings_module
    from src.workshop0.auth import oidc

    monkeypatch.setenv("WORKSHOP0_GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("WORKSHOP0_GOOGLE_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("WORKSHOP0_OIDC_ISSUER", fake_issuer.base_url)
    monkeypatch.setenv("WORKSHOP0_SESSION_SECRET", secrets.token_hex(32))
    monkeypatch.setenv("WORKSHOP0_ADMIN_EMAILS", ADMIN_EMAIL)
    settings_module._settings = None
    oidc.reset_caches()
    fake_issuer.reset()
    yield
    fake_issuer.reset()
    oidc.reset_caches()
