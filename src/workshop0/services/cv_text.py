"""Text extraction from CV files (pypdf / python-docx).

`extract_text(data, kind)` returns normalised plain text (whitespace collapsed per line,
at most one blank line in a row, NULs stripped), capped at 60000 characters
(`cv_document.text_extract`, spec/data-model.md). It raises `CvUnreadable` — mapped by
the API to 422 `cv_unreadable` ("paste your CV text instead") — when the file cannot be
parsed (corrupt, wrong type, encrypted) or yields fewer than 200 characters of text
(e.g. an image-only scan with no text layer).
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Literal

import structlog

MIN_TEXT_CHARS = 200
MAX_EXTRACT_CHARS = 60_000

log = structlog.get_logger("workshop0")
_SPACES_RE = re.compile(r"[ \t\f\v  -​　]+")
_BLANKS_RE = re.compile(r"\n{3,}")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")


class CvUnreadable(Exception):
    """No usable text (below 200 chars) — the API maps this to 422 `cv_unreadable`."""

    def __init__(self, message: str = "no extractable text", *, reason: str = "too_short") -> None:
        super().__init__(message)
        self.reason = reason  # corrupt | encrypted | too_short


def extract_text(data: bytes, kind: Literal["pdf", "docx"]) -> str:
    """Extracted plain text; raises CvUnreadable when it is unusable."""
    if kind == "pdf":
        raw = _pdf_text(data)
    elif kind == "docx":
        raw = _docx_text(data)
    else:
        raise ValueError(f"unsupported CV kind {kind!r} (expected 'pdf' or 'docx')")
    text = normalize_text(raw)
    if len(text) < MIN_TEXT_CHARS:
        raise CvUnreadable(
            f"only {len(text)} characters of text could be extracted", reason="too_short"
        )
    return text[:MAX_EXTRACT_CHARS]


def normalize_text(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_RE.sub("", text)
    lines = [_SPACES_RE.sub(" ", line).strip() for line in text.split("\n")]
    return _BLANKS_RE.sub("\n\n", "\n".join(lines)).strip()


def _pdf_text(data: bytes) -> str:
    if not data or not bytes(data[:1024]).lstrip().startswith(b"%PDF-"):
        raise CvUnreadable("not a PDF file", reason="corrupt")
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                if not reader.decrypt(""):
                    raise CvUnreadable("the PDF is password-protected", reason="encrypted")
            except CvUnreadable:
                raise
            except Exception as exc:
                raise CvUnreadable("the PDF is password-protected", reason="encrypted") from exc
        parts: list[str] = []
        total = 0
        for page in reader.pages:
            page_text = page.extract_text() or ""
            parts.append(page_text)
            total += len(page_text)
            if total > MAX_EXTRACT_CHARS * 2:  # enough text; stop parsing the rest
                break
    except CvUnreadable:
        raise
    except Exception as exc:  # malformed PDFs fail in many different ways
        log.info("cv_text.unreadable", kind="pdf", error=type(exc).__name__)
        raise CvUnreadable("the PDF could not be read", reason="corrupt") from exc
    return "\n".join(parts)


def _docx_text(data: bytes) -> str:
    if not data or not zipfile.is_zipfile(io.BytesIO(data)):
        raise CvUnreadable("not a DOCX file", reason="corrupt")
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
        parts: list[str] = []
        for section in document.sections:
            parts.extend(p.text for p in section.header.paragraphs)
        _collect_body(document.element.body, parts)
        for section in document.sections:
            parts.extend(p.text for p in section.footer.paragraphs)
    except Exception as exc:  # bad package, lxml errors, missing parts
        log.info("cv_text.unreadable", kind="docx", error=type(exc).__name__)
        raise CvUnreadable("the DOCX could not be read", reason="corrupt") from exc
    return "\n".join(parts)


_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _collect_body(element, parts: list[str]) -> None:
    """Paragraphs and table cells in document order (CVs often lay out skills in tables)."""
    for child in element.iterchildren():
        tag = child.tag
        if tag == f"{_W_NS}p":
            parts.append(_paragraph_text(child))
        elif tag == f"{_W_NS}tbl":
            for row in child.iter(f"{_W_NS}tr"):
                cells = []
                for cell in row.iterchildren(f"{_W_NS}tc"):
                    cells.append(
                        " ".join(_paragraph_text(p) for p in cell.iter(f"{_W_NS}p")).strip()
                    )
                parts.append(" | ".join(c for c in cells if c))
        elif tag == f"{_W_NS}sdt":
            content = child.find(f"{_W_NS}sdtContent")
            if content is not None:
                _collect_body(content, parts)


def _paragraph_text(p) -> str:
    chunks: list[str] = []
    for node in p.iter():
        if node.tag == f"{_W_NS}t" and node.text:
            chunks.append(node.text)
        elif node.tag == f"{_W_NS}tab":
            chunks.append(" ")
        elif node.tag in (f"{_W_NS}br", f"{_W_NS}cr"):
            chunks.append("\n")
    return "".join(chunks)
