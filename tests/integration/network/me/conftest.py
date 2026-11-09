"""Fixtures for the `/api/me/*` suite (slice S7). Blobs go to a per-test directory."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def blob_root(tmp_path, monkeypatch):
    """Local blob backend rooted in a per-test directory (never the repo's data/blobs)."""
    import src.workshop0.config.settings as settings_module
    from src.workshop0.storage import blobstore

    root = tmp_path / "blobs"
    root.mkdir()
    monkeypatch.setenv("WORKSHOP0_BLOB_BACKEND", "local")
    monkeypatch.setattr(blobstore, "DEFAULT_LOCAL_ROOT", root)
    settings_module._settings = None
    return root


@pytest.fixture
def trainer(make_user, signed_in_client):
    """(user, client) for a fresh signed-in trainer without a profile."""
    user = make_user("trainer@example.test")
    return user, signed_in_client(user)
