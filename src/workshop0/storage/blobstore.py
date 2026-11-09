"""CV blob storage: local disk (`data/blobs/`) or a private GCS bucket.

Interface stub laid down by the Phase-11 shared scaffold; filled by slice S4 (cv-ingest).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from fastapi import Response


@runtime_checkable
class BlobStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def download_response(self, key: str, filename: str) -> Response: ...


class LocalDiskStore:
    """Files under `root`; downloads stream with `Content-Disposition: attachment`."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        raise NotImplementedError

    def get(self, key: str) -> bytes:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def download_response(self, key: str, filename: str) -> Response:
        raise NotImplementedError


class GcsStore:
    """Objects in a private bucket; downloads are a 307 to a 5-minute V4 signed URL."""

    def __init__(self, bucket: str) -> None:
        self.bucket = bucket

    def put(self, key: str, data: bytes, content_type: str) -> None:
        raise NotImplementedError

    def get(self, key: str) -> bytes:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def download_response(self, key: str, filename: str) -> Response:
        raise NotImplementedError


def get_blobstore() -> BlobStore:
    """The configured backend (`WORKSHOP0_BLOB_BACKEND`: `local` default, `gcs` in production)."""
    raise NotImplementedError
