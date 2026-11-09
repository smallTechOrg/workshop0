"""get_blobstore() backend selection, and GcsStore behaviour.

- Selection and GcsStore logic run offline: an in-memory stand-in for the GCS client, and
  a real `google.cloud.storage.Client` with a throwaway, locally generated service-account
  key so V4 signing happens on this machine (no network, no bucket, no gcloud).
- The live round-trip at the bottom runs only when WORKSHOP0_GCS_BUCKET names an existing
  bucket the ambient credentials can write to. It never creates buckets.
"""

from __future__ import annotations

import os
import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.workshop0.config.settings import Settings
from src.workshop0.storage import blobstore
from src.workshop0.storage.blobstore import (
    SIGNED_URL_TTL,
    BlobNotFound,
    BlobStore,
    GcsStore,
    InvalidBlobKey,
    LocalDiskStore,
    get_blobstore,
)

# --------------------------------------------------------------------------- selection


def test_settings_default_backend_is_local():
    assert Settings.model_fields["workshop0_blob_backend"].default == "local"


@pytest.mark.parametrize("value", ["local", "LOCAL", " local ", ""])
def test_local_backend_uses_the_default_root(use_backend, value):
    use_backend(value)
    store = get_blobstore()
    assert isinstance(store, LocalDiskStore)
    assert store.root == blobstore.DEFAULT_LOCAL_ROOT
    store.put("cv/1/a.pdf", b"x", "application/pdf")
    assert (blobstore.DEFAULT_LOCAL_ROOT / "cv" / "1" / "a.pdf").read_bytes() == b"x"


def test_repo_default_local_root_is_under_gitignored_data():
    assert blobstore.DEFAULT_LOCAL_ROOT.parts == ("data", "blobs")


def test_gcs_backend_returns_one_cached_lazy_store_per_bucket(use_backend):
    use_backend("gcs", "workshop0-cvs-test")
    first = get_blobstore()
    assert isinstance(first, GcsStore) and isinstance(first, BlobStore)
    assert first.bucket == "workshop0-cvs-test"
    assert first._client is None  # no client (and no credentials lookup) until first use
    assert get_blobstore() is first
    blobstore.reset_blobstore()
    assert get_blobstore() is not first


def test_gcs_backend_without_a_bucket_is_refused(use_backend):
    use_backend("gcs", "  ")
    with pytest.raises(ValueError, match="WORKSHOP0_GCS_BUCKET"):
        get_blobstore()


def test_unknown_backend_is_refused(use_backend):
    use_backend("s3")
    with pytest.raises(ValueError, match="unknown WORKSHOP0_BLOB_BACKEND"):
        get_blobstore()


def test_gcs_store_needs_a_bucket_name():
    with pytest.raises(ValueError):
        GcsStore("")


# --------------------------------------------------------------------------- GcsStore (offline)


class _FakeBlob:
    def __init__(self, objects: dict, name: str) -> None:
        self.objects, self.name = objects, name

    def upload_from_string(self, data, content_type=None):
        assert isinstance(data, bytes)
        self.objects[self.name] = (data, content_type)

    def download_as_bytes(self):
        from google.api_core.exceptions import NotFound

        if self.name not in self.objects:
            raise NotFound("no such object")
        return self.objects[self.name][0]

    def delete(self):
        from google.api_core.exceptions import NotFound

        if self.objects.pop(self.name, None) is None:
            raise NotFound("no such object")


class _FakeClient:
    def __init__(self) -> None:
        self.objects: dict = {}
        self.buckets: list[str] = []

    def bucket(self, name):
        self.buckets.append(name)
        client = self

        class _Bucket:
            def blob(self, key):
                return _FakeBlob(client.objects, key)

        return _Bucket()


def test_gcs_round_trip_and_not_found_mapping():
    client = _FakeClient()
    store = GcsStore("cv-bucket", client=client)
    store.put("cv/4/a.pdf", bytearray(b"%PDF-1.4 data"), "application/pdf")
    assert client.objects["cv/4/a.pdf"] == (b"%PDF-1.4 data", "application/pdf")
    assert store.get("cv/4/a.pdf") == b"%PDF-1.4 data"
    assert set(client.buckets) == {"cv-bucket"}
    store.delete("cv/4/a.pdf")
    with pytest.raises(BlobNotFound):
        store.get("cv/4/a.pdf")
    store.delete("cv/4/a.pdf")  # idempotent, like the local store


@pytest.mark.parametrize("key", ["../x.pdf", "/abs.pdf", "cv//x.pdf", ""])
def test_gcs_refuses_unsafe_keys(key):
    client = _FakeClient()
    store = GcsStore("cv-bucket", client=client)
    for call in (lambda: store.put(key, b"x", "application/pdf"), lambda: store.get(key), lambda: store.delete(key)):
        with pytest.raises(InvalidBlobKey):
            call()
    assert client.objects == {}


@pytest.fixture(scope="module")
def signing_client():
    """A real storage.Client whose credentials hold a locally generated RSA key (never used online)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from google.cloud import storage
    from google.oauth2 import service_account

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    credentials = service_account.Credentials.from_service_account_info(
        {
            "type": "service_account",
            "project_id": "workshop0-test",
            "private_key_id": "test-key",
            "private_key": pem,
            "client_email": "workshop0-run@workshop0-test.iam.gserviceaccount.com",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )
    return storage.Client(project="workshop0-test", credentials=credentials)


def test_signed_url_is_v4_five_minutes_with_attachment_disposition(signing_client):
    assert SIGNED_URL_TTL == timedelta(minutes=5)
    store = GcsStore("workshop0-cvs", client=signing_client)
    url = store.signed_url("cv/12/abc.pdf", "Priyā CV.pdf")
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https" and parsed.netloc == "storage.googleapis.com"
    assert parsed.path == "/workshop0-cvs/cv/12/abc.pdf"
    assert query["X-Goog-Algorithm"] == ["GOOG4-RSA-SHA256"]
    assert query["X-Goog-Expires"] == ["300"]
    assert query["X-Goog-Credential"][0].startswith("workshop0-run@workshop0-test.iam.gserviceaccount.com/")
    assert query["response-content-disposition"][0].startswith('attachment; filename="Priy_ CV.pdf"')
    assert query["response-content-type"] == ["application/pdf"]
    assert query["X-Goog-Signature"][0]


def test_gcs_download_is_a_307_to_the_signed_url(signing_client):
    store = GcsStore("workshop0-cvs", client=signing_client)
    app = FastAPI()

    @app.get("/file")
    def file():
        return store.download_response("cv/12/abc.docx", "arjun.docx")

    response = TestClient(app).get("/file", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://storage.googleapis.com/workshop0-cvs/cv/12/abc.docx?")
    assert "X-Goog-Expires=300" in location
    assert response.headers["cache-control"] == "private, no-store"


def test_gcs_signed_url_refuses_unsafe_keys(signing_client):
    store = GcsStore("workshop0-cvs", client=signing_client)
    with pytest.raises(InvalidBlobKey):
        store.signed_url("../other-bucket/x.pdf", "x.pdf")


# --------------------------------------------------------------------------- live GCS (guarded)

LIVE_BUCKET = os.environ.get("WORKSHOP0_GCS_BUCKET", "").strip()


@pytest.mark.skipif(not LIVE_BUCKET, reason="WORKSHOP0_GCS_BUCKET not set; live GCS test is opt-in")
def test_live_gcs_round_trip_and_signed_download(use_backend):
    import httpx

    use_backend("gcs", LIVE_BUCKET)
    store = get_blobstore()
    key = f"cv/test-s4/{uuid.uuid4()}.pdf"
    payload = b"%PDF-1.4 workshop0 live blob test " + uuid.uuid4().bytes
    try:
        store.put(key, payload, "application/pdf")
        assert store.get(key) == payload
        response = httpx.get(store.signed_url(key, "live test.pdf"), timeout=20)
        assert response.status_code == 200 and response.content == payload
        assert response.headers["content-disposition"].startswith("attachment;")
    finally:
        store.delete(key)
    with pytest.raises(BlobNotFound):
        store.get(key)
