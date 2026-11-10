"""Phase 13: signed unsubscribe tokens (slice D1 implements)."""

from __future__ import annotations

from typing import Literal


def make_token(user_id: int, kind: Literal["alerts", "digest"]) -> str:
    raise NotImplementedError


def read_token(token: str) -> tuple[int, str]:
    """Raises ValueError on a bad token."""
    raise NotImplementedError


def url(base_url: str, user_id: int, kind: str) -> str:
    raise NotImplementedError
