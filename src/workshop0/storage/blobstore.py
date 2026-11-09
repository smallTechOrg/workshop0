"""CV blob storage: local disk (`data/blobs/`) or a private GCS bucket.

spec/architecture.md §CV storage. One `BlobStore` interface, two backends:

- `LocalDiskStore(root)` — dev/tests. Keys map to files under `root`; every key is
  validated and the resolved path must stay inside `root` (path-traversal safe).
  Writes are atomic (temp file in the target directory + fsync + `os.replace`).
  Downloads are a streamed `FileResponse` with `Content-Disposition: attachment`.
- `GcsStore(bucket)` — production. Objects in a private bucket; downloads are a
  307 to a 5-minute V4 signed URL. On Cloud Run there is no key file: the URL is
  signed through the IAM `signBlob` API with the runtime service account's own
  access token.

`get_blobstore()` picks the backend from `WORKSHOP0_BLOB_BACKEND` (`local` default,
`gcs` with `WORKSHOP0_GCS_BUCKET`).
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote

from fastapi import Response
from fastapi.responses import FileResponse, RedirectResponse

from src.workshop0.config.settings import get_settings

DEFAULT_LOCAL_ROOT = Path("data") / "blobs"
SIGNED_URL_TTL = timedelta(minutes=5)
MAX_KEY_LENGTH = 300  # cv_document.storage_key is String(300)

# A key is a relative, '/'-separated path of safe segments, e.g. `cv/12/<uuid>.pdf`.
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_GCP_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)


class InvalidBlobKey(ValueError):
    """The key is not a safe relative path (traversal, absolute, odd characters)."""


class BlobNotFound(FileNotFoundError):
    """No blob is stored under the key."""


@runtime_checkable
class BlobStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def download_response(self, key: str, filename: str) -> Response: ...


def validate_key(key: str) -> str:
    """Return `key` unchanged if it is a safe relative blob key, else raise InvalidBlobKey."""
    if not isinstance(key, str) or not key or len(key) > MAX_KEY_LENGTH:
        raise InvalidBlobKey("blob key must be 1-300 characters")
    segments = key.split("/")
    for segment in segments:
        if segment in ("", ".", "..") or not _SEGMENT_RE.match(segment):
            raise InvalidBlobKey("blob key contains an unsafe path segment")
    return key


def _ascii_fallback(filename: str) -> str:
    cleaned = "".join(ch if 32 <= ord(ch) < 127 and ch not in '"\\/' else "_" for ch in filename)
    cleaned = cleaned.strip(" .") or "download"
    return cleaned[:150]


def safe_download_name(filename: str) -> str:
    """The user-supplied original filename reduced to a safe base name (no paths, no controls)."""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch.isprintable() and ch not in "\r\n\t")
    name = name.strip(" .")
    return name[:150] or "download"


def content_disposition(filename: str) -> str:
    """`attachment` header value: an ASCII `filename=` plus an RFC 5987 `filename*=` for UTF-8."""
    name = safe_download_name(filename)
    return f"attachment; filename=\"{_ascii_fallback(name)}\"; filename*=UTF-8''{quote(name, safe='')}"


_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _media_type_for(filename: str) -> str:
    """Only the CV types get a specific type; anything else (e.g. `x.html`) is opaque bytes."""
    return _MEDIA_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")


_DOWNLOAD_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
}


class LocalDiskStore:
    """Files under `root`; downloads stream with `Content-Disposition: attachment`."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        validate_key(key)
        root = self.root.resolve()
        path = (root / key).resolve()
        if not path.is_relative_to(root) or path == root:
            raise InvalidBlobKey("blob key escapes the storage root")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".part")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(bytes(data))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return path.read_bytes()
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError) as exc:
            raise BlobNotFound(key) from exc

    def delete(self, key: str) -> None:
        """Remove the blob (idempotent) and prune now-empty parent directories under root."""
        path = self._path(key)
        try:
            path.unlink()
        except FileNotFoundError:
            return
        root = self.root.resolve()
        parent = path.parent
        while parent != root and parent.is_relative_to(root):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def download_response(self, key: str, filename: str) -> Response:
        path = self._path(key)
        if not path.is_file():
            raise BlobNotFound(key)
        name = safe_download_name(filename)
        headers = {"Content-Disposition": content_disposition(name), **_DOWNLOAD_HEADERS}
        return FileResponse(path, media_type=_media_type_for(name), headers=headers)


class GcsStore:
    """Objects in a private bucket; downloads are a 307 to a 5-minute V4 signed URL."""

    def __init__(self, bucket: str, *, client: Any | None = None) -> None:
        if not bucket:
            raise ValueError("GcsStore needs a bucket name (WORKSHOP0_GCS_BUCKET)")
        self.bucket = bucket
        self._client = client
        self._lock = threading.Lock()

    def _bucket(self) -> Any:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    from google.cloud import storage

                    self._client = storage.Client()
        return self._client.bucket(self.bucket)

    def _blob(self, key: str) -> Any:
        return self._bucket().blob(validate_key(key))

    def put(self, key: str, data: bytes, content_type: str) -> None:
        # A single-request upload is atomic in GCS: readers see the old object or the new one.
        self._blob(key).upload_from_string(bytes(data), content_type=content_type)

    def get(self, key: str) -> bytes:
        from google.api_core.exceptions import NotFound

        try:
            return self._blob(key).download_as_bytes()
        except NotFound as exc:
            raise BlobNotFound(key) from exc

    def delete(self, key: str) -> None:
        from google.api_core.exceptions import NotFound

        try:
            self._blob(key).delete()
        except NotFound:
            return

    def signed_url(self, key: str, filename: str) -> str:
        blob = self._blob(key)
        name = safe_download_name(filename)
        kwargs: dict[str, Any] = {
            "version": "v4",
            "expiration": SIGNED_URL_TTL,
            "method": "GET",
            "response_disposition": content_disposition(name),
            "response_type": _media_type_for(name),
        }
        credentials = getattr(self._client, "_credentials", None)
        if not _can_sign_locally(credentials):
            # Cloud Run: no private key — sign via IAM signBlob with the runtime SA's own token.
            import google.auth
            import google.auth.transport.requests

            creds, _ = google.auth.default(scopes=list(_GCP_SCOPES))
            creds.refresh(google.auth.transport.requests.Request())
            kwargs["service_account_email"] = creds.service_account_email
            kwargs["access_token"] = creds.token
        return blob.generate_signed_url(**kwargs)

    def download_response(self, key: str, filename: str) -> Response:
        return RedirectResponse(
            self.signed_url(key, filename), status_code=307, headers=dict(_DOWNLOAD_HEADERS)
        )


def _can_sign_locally(credentials: Any) -> bool:
    """True when the credentials carry a private key (e.g. a service-account key file)."""
    from google.auth import credentials as ga_credentials

    return isinstance(credentials, ga_credentials.Signing) and getattr(
        credentials, "signer", None
    ) is not None


_gcs_stores: dict[str, GcsStore] = {}
_gcs_lock = threading.Lock()


def get_blobstore() -> BlobStore:
    """The configured backend (`WORKSHOP0_BLOB_BACKEND`: `local` default, `gcs` in production)."""
    settings = get_settings()
    backend = (settings.workshop0_blob_backend or "local").strip().lower()
    if backend == "local":
        return LocalDiskStore(DEFAULT_LOCAL_ROOT)
    if backend == "gcs":
        bucket = (settings.workshop0_gcs_bucket or "").strip()
        if not bucket:
            raise ValueError("WORKSHOP0_BLOB_BACKEND=gcs requires WORKSHOP0_GCS_BUCKET")
        with _gcs_lock:
            store = _gcs_stores.get(bucket)
            if store is None:
                store = _gcs_stores[bucket] = GcsStore(bucket)
        return store
    raise ValueError(f"unknown WORKSHOP0_BLOB_BACKEND {backend!r} (expected 'local' or 'gcs')")


def reset_blobstore() -> None:
    """Drop cached GCS clients (tests)."""
    with _gcs_lock:
        _gcs_stores.clear()
