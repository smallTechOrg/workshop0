"""Stateless DB-backed rate limiting over `rate_limit_hit`.

spec/architecture.md §Network identity; data-model.md §rate_limit_hit.

Fixed-window counter: every hit lands in the row `(bucket, window_start)` where
`window_start = floor(now / window_s) * window_s` (UTC epoch seconds). The increment is one
atomic dialect upsert —

    INSERT … ON CONFLICT (bucket, window_start) DO UPDATE SET count = count + 1 RETURNING count

— so concurrent hits from any number of app instances sharing the database are counted
exactly once each (the DB is the only shared state; nothing lives in process memory).

Transaction semantics. On PostgreSQL (or any server DB) the hit is written and COMMITTED in its
own short transaction on a fresh pooled connection, independent of the caller's request
transaction: the upsert's row lock is held for milliseconds, not for the whole request (a
global bucket such as the 600/h drafting guard must never serialize requests), and a hit counts
even if the request later fails. On SQLite (single-process local dev, one writer at a time) the
hit is executed inside the caller's session so it never contends with the caller's own write
lock; the request's commit persists it. A session bound to an explicit Connection (test
harness transactions) also uses the caller's session.

Housekeeping (data-model.md §rate_limit_hit): rows whose window started more than 24 h ago are
deleted opportunistically on ~1 in 100 hits.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.workshop0.db.models import RateLimitHit

log = structlog.get_logger("workshop0")

BUCKET_MAX_LEN = 120  # rate_limit_hit.bucket is String(120)
CLEANUP_PROBABILITY = 0.01  # "1 in 100 hits"
RETENTION = timedelta(hours=24)

# Indirection so tests can force / suppress the opportunistic cleanup deterministically.
_random = random.random


@dataclass(frozen=True)
class RateResult:
    allowed: bool
    retry_after_s: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def window_start_for(now: datetime, window_s: int) -> datetime:
    """Start of the fixed window containing `now`, aligned to the UTC epoch."""
    epoch = _as_utc(now).timestamp()
    start = math.floor(epoch / window_s) * window_s
    return datetime.fromtimestamp(start, tz=timezone.utc)


def retry_after_for(now: datetime, window_s: int) -> int:
    """Whole seconds until the current window ends (ceil; always >= 1)."""
    end = window_start_for(now, window_s) + timedelta(seconds=window_s)
    remaining = (end - _as_utc(now)).total_seconds()
    return max(1, math.ceil(remaining))


def _validate(bucket: str, limit: int, window_s: int) -> None:
    if not bucket or len(bucket) > BUCKET_MAX_LEN:
        raise ValueError(f"rate-limit bucket must be 1..{BUCKET_MAX_LEN} chars, got {len(bucket)}")
    if limit < 1:
        raise ValueError(f"rate-limit limit must be >= 1, got {limit}")
    if window_s < 1:
        raise ValueError(f"rate-limit window_s must be >= 1, got {window_s}")


def _upsert_statement(dialect_name: str, bucket: str, window_start: datetime):
    if dialect_name == "postgresql":
        insert = postgresql.insert
    elif dialect_name == "sqlite":
        insert = sqlite.insert
    else:  # pragma: no cover - the app supports PostgreSQL (prod/tests) and SQLite (local dev)
        raise RuntimeError(f"rate limiting does not support dialect {dialect_name!r}")
    table = RateLimitHit.__table__
    stmt = insert(table).values(bucket=bucket, window_start=window_start, count=1)
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.bucket, table.c.window_start],
        set_={"count": table.c.count + 1},
    )
    return stmt.returning(table.c.count)


def _cleanup_statement(now: datetime):
    return delete(RateLimitHit).where(RateLimitHit.window_start < now - RETENTION)


def _run(executor, dialect_name: str, bucket: str, window_start: datetime, now: datetime) -> int:
    count = executor.execute(_upsert_statement(dialect_name, bucket, window_start)).scalar_one()
    if _random() < CLEANUP_PROBABILITY:
        executor.execute(_cleanup_statement(now))
    return int(count)


def hit(
    session: Session,
    bucket: str,
    limit: int,
    window_s: int,
    *,
    now: datetime | None = None,
) -> RateResult:
    """Record one hit in `bucket` and report whether it is within `limit` per `window_s`.

    `allowed` is True for the first `limit` hits of the current window. `retry_after_s` is the
    whole number of seconds until the window ends when blocked, and 0 when allowed.
    """
    _validate(bucket, limit, window_s)
    current = _as_utc(now) if now is not None else _utcnow()
    window_start = window_start_for(current, window_s)

    bind = session.get_bind()
    dialect_name = bind.dialect.name
    if isinstance(bind, Engine) and dialect_name != "sqlite":
        with bind.begin() as connection:  # own short transaction, committed on exit
            count = _run(connection, dialect_name, bucket, window_start, current)
    else:
        count = _run(session, dialect_name, bucket, window_start, current)

    if count <= limit:
        return RateResult(allowed=True, retry_after_s=0)
    retry_after = retry_after_for(current, window_s)
    log.info(
        "ratelimit.blocked",
        bucket=bucket,
        limit=limit,
        window_s=window_s,
        count=count,
        retry_after_s=retry_after,
    )
    return RateResult(allowed=False, retry_after_s=retry_after)


def enforce(
    session: Session,
    bucket: str,
    limit: int,
    window_s: int,
    *,
    now: datetime | None = None,
) -> None:
    """`hit`, raising 429 `rate_limited` with a `Retry-After` header when over the limit.

    The error uses the app's envelope (`{"detail": {"code", "message"}}`, as `api_error`).
    """
    result = hit(session, bucket, limit, window_s, now=now)
    if result.allowed:
        return
    seconds = result.retry_after_s
    raise HTTPException(
        status_code=429,
        detail={
            "code": "rate_limited",
            "message": f"Too many requests — try again in {_human(seconds)}.",
        },
        headers={"Retry-After": str(seconds)},
    )


def _human(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = math.ceil(seconds / 60)
    return f"{minutes} minute{'s' if minutes != 1 else ''}"
