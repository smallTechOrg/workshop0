"""LocalDiskStore: round-trip, traversal refusal, atomic writes, delete, and the streamed
download with `Content-Disposition: attachment` (architecture.md §CV storage)."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.workshop0.storage import blobstore
from src.workshop0.storage.blobstore import (
    BlobNotFound,
    BlobStore,
    InvalidBlobKey,
    LocalDiskStore,
    content_disposition,
    safe_download_name,
    validate_key,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "cv"
PDF = (FIXTURES / "genai_trainer.pdf").read_bytes()
DOCX = (FIXTURES / "devops_trainer.docx").read_bytes()
KEY = "cv/12/0b9f4c2e-6d1a-4c55-9a3e-2f7b8d1e4a10.pdf"


def _download(store: LocalDiskStore, key: str, filename: str):
    app = FastAPI()

    @app.get("/file")
    def file():
        return store.download_response(key, filename)

    return TestClient(app).get("/file")


def _all_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


# --------------------------------------------------------------------------- happy paths


def test_local_store_satisfies_the_protocol(store):
    assert isinstance(store, BlobStore)


def test_put_get_round_trip_creates_nested_dirs(store):
    store.put(KEY, PDF, "application/pdf")
    assert store.get(KEY) == PDF
    assert (store.root / "cv" / "12").is_dir()
    assert store.exists(KEY)
    assert _all_files(store.root) == [store.root / KEY]  # no temp files left behind


def test_put_overwrites_the_previous_blob(store):
    store.put(KEY, PDF, "application/pdf")
    store.put(KEY, b"%PDF-1.4 replacement", "application/pdf")
    assert store.get(KEY) == b"%PDF-1.4 replacement"
    assert len(_all_files(store.root)) == 1


def test_bytearray_and_memoryview_are_accepted(store):
    store.put("cv/1/a.pdf", bytearray(b"abc"), "application/pdf")
    store.put("cv/1/b.pdf", memoryview(b"def"), "application/pdf")
    assert store.get("cv/1/a.pdf") == b"abc" and store.get("cv/1/b.pdf") == b"def"


def test_delete_removes_blob_and_prunes_empty_dirs_but_keeps_root_and_siblings(store):
    store.put("cv/7/one.pdf", PDF, "application/pdf")
    store.put("cv/8/two.docx", DOCX, "application/octet-stream")
    store.delete("cv/7/one.pdf")
    assert not store.exists("cv/7/one.pdf")
    assert not (store.root / "cv" / "7").exists()
    assert store.get("cv/8/two.docx") == DOCX
    store.delete("cv/8/two.docx")
    assert store.root.is_dir() and list(store.root.iterdir()) == []


def test_download_streams_bytes_as_an_attachment(store):
    store.put(KEY, PDF, "application/pdf")
    response = _download(store, KEY, "Priya Raman CV.pdf")
    assert response.status_code == 200
    assert response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert 'filename="Priya Raman CV.pdf"' in disposition
    assert "filename*=UTF-8''Priya%20Raman%20CV.pdf" in disposition
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_download_media_type_comes_from_an_allow_list(store):
    store.put(KEY, PDF, "application/pdf")
    response = _download(store, KEY, "cv.html")  # an attacker-chosen original name
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")


def test_download_docx_media_type(store):
    store.put("cv/3/x.docx", DOCX, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    response = _download(store, "cv/3/x.docx", "arjun.docx")
    assert response.status_code == 200 and response.content == DOCX
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


# --------------------------------------------------------------------------- edge cases


def test_unicode_filename_gets_ascii_fallback_and_rfc5987_form():
    value = content_disposition("Priyā Rāman – CV.pdf")
    assert value.startswith('attachment; filename="Priy_ R_man _ CV.pdf"; ')
    assert "filename*=UTF-8''Priy%C4%81%20R%C4%81man%20%E2%80%93%20CV.pdf" in value
    value.encode("latin-1")  # a header value must be latin-1 encodable


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\cv.pdf", "cv.pdf"),
        ("evil\r\nSet-Cookie: x=1.pdf", "evilSet-Cookie: x=1.pdf"),
        ("", "download"),
        ("...", "download"),
        ("a" * 400 + ".pdf", "a" * 150),
    ],
)
def test_safe_download_name_strips_paths_and_controls(raw, expected):
    assert safe_download_name(raw) == expected


def test_header_injection_in_filename_never_reaches_the_response(store):
    store.put(KEY, PDF, "application/pdf")
    response = _download(store, KEY, 'x"; filename=evil.exe\r\nX-Evil: 1')
    assert response.status_code == 200
    assert "x-evil" not in response.headers
    disposition = response.headers["content-disposition"]
    # the quote was neutralised, so the injected text stays inside the one quoted-string
    assert re.fullmatch(r'attachment; filename="[^"\\]*"; filename\*=UTF-8\'\'[A-Za-z0-9%._~-]*', disposition)
    assert "\r" not in disposition and "\n" not in disposition


def test_quoted_names_cannot_break_out_of_the_quoted_string():
    value = content_disposition('a"b;c.pdf')
    assert value.startswith('attachment; filename="a_b;c.pdf"; filename*=UTF-8\'\'a%22b%3Bc.pdf')
    assert content_disposition("dir\\sub\\c.pdf").startswith('attachment; filename="c.pdf"')


def test_key_length_limit_matches_the_storage_key_column(store):
    prefix = "cv/" + "a" * 100 + "/" + "b" * 100 + "/"
    long_key = prefix + "c" * (300 - len(prefix) - 4) + ".pdf"
    assert len(long_key) == 300
    store.put(long_key, b"x", "application/pdf")
    assert store.get(long_key) == b"x"
    with pytest.raises(InvalidBlobKey):
        validate_key(long_key + "f")


# --------------------------------------------------------------------------- error paths


@pytest.mark.parametrize(
    "key",
    [
        "",
        ".",
        "..",
        "../outside.pdf",
        "cv/../../outside.pdf",
        "cv/12/../../../etc/passwd",
        "/etc/passwd",
        "cv//12.pdf",
        "cv/./12.pdf",
        "cv/12/",
        "cv\\..\\outside.pdf",
        "cv/12/x.pdf\x00.txt",
        "cv/12/.hidden",
        "cv/12/name with space.pdf",
        "~/cv.pdf",
        "cv/%2e%2e/x.pdf",
    ],
)
def test_unsafe_keys_are_refused_by_every_operation(store, key):
    for call in (
        lambda: store.put(key, b"x", "application/pdf"),
        lambda: store.get(key),
        lambda: store.delete(key),
        lambda: store.exists(key),
        lambda: store.download_response(key, "x.pdf"),
    ):
        with pytest.raises(InvalidBlobKey):
            call()
    assert _all_files(store.root) == []


def test_non_string_key_is_refused(store):
    with pytest.raises(InvalidBlobKey):
        store.get(None)  # type: ignore[arg-type]


def test_symlink_escaping_the_root_is_refused(store, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.pdf").write_bytes(b"secret")
    os.symlink(outside, store.root / "cv")
    with pytest.raises(InvalidBlobKey):
        store.get("cv/secret.pdf")
    with pytest.raises(InvalidBlobKey):
        store.put("cv/new.pdf", b"x", "application/pdf")
    assert sorted(p.name for p in outside.iterdir()) == ["secret.pdf"]


def test_missing_blob_raises_not_found_and_delete_is_idempotent(store):
    with pytest.raises(BlobNotFound):
        store.get("cv/1/missing.pdf")
    with pytest.raises(BlobNotFound):
        store.download_response("cv/1/missing.pdf", "x.pdf")
    store.delete("cv/1/missing.pdf")  # no error
    assert not store.exists("cv/1/missing.pdf")
    assert issubclass(BlobNotFound, FileNotFoundError)


def test_a_directory_is_not_a_blob(store):
    store.put("cv/5/a.pdf", b"x", "application/pdf")
    with pytest.raises(BlobNotFound):
        store.get("cv/5")
    with pytest.raises(BlobNotFound):
        store.download_response("cv/5", "x.pdf")


def test_failed_write_keeps_the_old_blob_and_leaves_no_temp_file(store, monkeypatch):
    store.put(KEY, PDF, "application/pdf")

    def boom(src, dst):
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(blobstore.os, "replace", boom)
        with pytest.raises(OSError, match="disk full"):
            store.put(KEY, b"half-written", "application/pdf")
    assert store.get(KEY) == PDF
    assert _all_files(store.root) == [store.root / KEY]


def test_failed_first_write_leaves_nothing_behind(store, monkeypatch):
    def boom(fd):
        raise OSError("io error")

    with monkeypatch.context() as patch:
        patch.setattr(blobstore.os, "fsync", boom)
        with pytest.raises(OSError, match="io error"):
            store.put("cv/9/new.pdf", PDF, "application/pdf")
    assert _all_files(store.root) == []
    assert not store.exists("cv/9/new.pdf")


def test_write_goes_through_a_temp_file_in_the_target_directory(store, monkeypatch):
    seen: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy(src, dst):
        seen.append((str(src), str(dst)))
        assert Path(src).read_bytes() == PDF  # fully written + fsynced before the rename
        real_replace(src, dst)

    with monkeypatch.context() as patch:
        patch.setattr(blobstore.os, "replace", spy)
        store.put(KEY, PDF, "application/pdf")
    [(src, dst)] = seen
    assert Path(src).parent == Path(dst).parent == (store.root / KEY).resolve().parent
    assert Path(src).name.startswith(".tmp-")
