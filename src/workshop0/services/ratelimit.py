"""Stateless DB-backed rate limiting over `rate_limit_hit` (spec/architecture.md §Network identity).

Interface stub laid down by the Phase-11 shared scaffold; filled by slice S2 (ratelimit).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class RateResult:
    allowed: bool
    retry_after_s: int


def hit(session: Session, bucket: str, limit: int, window_s: int) -> RateResult:
    """Record one hit in `bucket` and report whether it is within `limit` per `window_s`."""
    raise NotImplementedError


def enforce(session: Session, bucket: str, limit: int, window_s: int) -> None:
    """`hit`, raising 429 `rate_limited` with a `Retry-After` header when over the limit."""
    raise NotImplementedError
