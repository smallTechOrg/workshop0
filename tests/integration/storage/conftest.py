"""Fixtures for the blob-store suite (slice S4). Every local store lives in a per-test
directory, never the repo's data/blobs; the backend is chosen via env + a settings reset."""

from __future__ import annotations

import pytest


@pytest.fixture
def store(tmp_path):
    from src.workshop0.storage.blobstore import LocalDiskStore

    root = tmp_path / "blobs"
    root.mkdir()
    return LocalDiskStore(root)


@pytest.fixture
def use_backend(monkeypatch, tmp_path):
    """use_backend(backend, bucket="") → sets the env the settings read and resets caches."""
    import src.workshop0.config.settings as settings_module
    from src.workshop0.storage import blobstore

    monkeypatch.setattr(blobstore, "DEFAULT_LOCAL_ROOT", tmp_path / "default-blobs")

    def _use(backend: str, bucket: str = "") -> None:
        monkeypatch.setenv("WORKSHOP0_BLOB_BACKEND", backend)
        monkeypatch.setenv("WORKSHOP0_GCS_BUCKET", bucket)
        settings_module._settings = None
        blobstore.reset_blobstore()

    yield _use
    blobstore.reset_blobstore()
