"""Text extraction from CV files (pypdf / python-docx).

Interface stub laid down by the Phase-11 shared scaffold; filled by slice S4 (cv-ingest).
"""

from __future__ import annotations

from typing import Literal


class CvUnreadable(Exception):
    """No usable text (below 200 chars) — the API maps this to 422 `cv_unreadable`."""


def extract_text(data: bytes, kind: Literal["pdf", "docx"]) -> str:
    """Extracted plain text; raises CvUnreadable when it is unusable."""
    raise NotImplementedError
