"""Unit tests for services/ratelimit.py: window math, Retry-After, validation, the 429 envelope.

The SQLite cases here cover the **local-dev dialect path** (SQLite is a supported local-dev
database for this app). They do not stand in for PostgreSQL: the production-driver behaviour,
including cross-instance enforcement, is in tests/integration/test_ratelimit_db.py.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.workshop0.db.models import RateLimitHit
from src.workshop0.services import ratelimit
from src.workshop0.services.ratelimit import (
    RateResult,
    enforce,
    hit,
    retry_after_for,
    window_start_for,
)

T0 = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)  # aligned to the hour and minute


# ------------------------------------------------------------------ window math


def test_window_start_aligns_to_epoch_buckets():
    assert window_start_for(T0, 3600) == T0
    assert window_start_for(T0 + timedelta(minutes=59, seconds=59), 3600) == T0
    assert window_start_for(T0 + timedelta(hours=1), 3600) == T0 + timedelta(hours=1)
    assert window_start_for(T0 + timedelta(seconds=61), 60) == T0 + timedelta(minutes=1)


def test_window_start_treats_naive_as_utc_and_converts_other_zones():
    naive = T0.replace(tzinfo=None) + timedelta(minutes=5)
    assert window_start_for(naive, 3600) == T0
    ist = timezone(timedelta(hours=5, minutes=30))
    assert window_start_for((T0 + timedelta(minutes=5)).astimezone(ist), 3600) == T0


def test_retry_after_counts_down_to_window_end():
    assert retry_after_for(T0, 3600) == 3600
    assert retry_after_for(T0 + timedelta(minutes=50), 3600) == 600
    assert retry_after_for(T0 + timedelta(seconds=59.2), 60) == 1  # ceil, never 0
    assert retry_after_for(T0 + timedelta(seconds=30.5), 60) == 30


# ------------------------------------------------------------------ validation (error path)


@pytest.mark.parametrize(
    ("bucket", "limit", "window_s"),
    [("", 10, 3600), ("x" * 121, 10, 3600), ("ok", 0, 3600), ("ok", 10, 0), ("ok", -1, 60)],
)
def test_invalid_arguments_are_rejected_before_touching_the_db(bucket, limit, window_s):
    with pytest.raises(ValueError):
        hit(None, bucket, limit, window_s)  # type: ignore[arg-type]  # never reaches the DB


def test_bucket_at_max_length_is_accepted(sqlite_session):
    assert hit(sqlite_session, "b" * 120, 1, 60, now=T0) == RateResult(True, 0)


# ------------------------------------------------------------------ SQLite dialect path


@pytest.fixture
def sqlite_session():
    engine = create_engine("sqlite://")
    RateLimitHit.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_sqlite_upsert_counts_and_blocks_after_limit(sqlite_session):
    now = T0 + timedelta(minutes=10)
    results = [hit(sqlite_session, "cv:user:1", 3, 3600, now=now) for _ in range(5)]
    assert [r.allowed for r in results] == [True, True, True, False, False]
    assert results[0].retry_after_s == 0
    assert results[3].retry_after_s == 50 * 60
    row = sqlite_session.execute(select(RateLimitHit)).scalar_one()
    assert (row.bucket, row.count) == ("cv:user:1", 5)


def test_sqlite_buckets_and_windows_are_independent(sqlite_session):
    assert hit(sqlite_session, "a", 1, 60, now=T0).allowed
    assert not hit(sqlite_session, "a", 1, 60, now=T0 + timedelta(seconds=30)).allowed
    assert hit(sqlite_session, "b", 1, 60, now=T0 + timedelta(seconds=30)).allowed
    assert hit(sqlite_session, "a", 1, 60, now=T0 + timedelta(seconds=60)).allowed  # rollover


def test_enforce_raises_429_rate_limited_with_retry_after(sqlite_session):
    now = T0 + timedelta(minutes=59, seconds=15)
    enforce(sqlite_session, "oidc:ip:1.2.3.4", 1, 3600, now=now)
    with pytest.raises(HTTPException) as excinfo:
        enforce(sqlite_session, "oidc:ip:1.2.3.4", 1, 3600, now=now)
    exc = excinfo.value
    assert exc.status_code == 429
    assert exc.detail["code"] == "rate_limited"
    assert "45 seconds" in exc.detail["message"]
    assert exc.headers == {"Retry-After": "45"}


def test_opportunistic_cleanup_deletes_only_rows_older_than_24h(sqlite_session, monkeypatch):
    monkeypatch.setattr(ratelimit, "_random", lambda: 0.99)  # no cleanup while seeding
    hit(sqlite_session, "old", 5, 60, now=T0 - timedelta(hours=25))
    hit(sqlite_session, "recent", 5, 60, now=T0 - timedelta(hours=23))
    assert len(sqlite_session.execute(select(RateLimitHit)).scalars().all()) == 2

    monkeypatch.setattr(ratelimit, "_random", lambda: 0.0)  # force the 1-in-100 branch
    hit(sqlite_session, "now", 5, 60, now=T0)
    buckets = sorted(r.bucket for r in sqlite_session.execute(select(RateLimitHit)).scalars())
    assert buckets == ["now", "recent"]


def test_cleanup_probability_is_one_in_a_hundred():
    assert ratelimit.CLEANUP_PROBABILITY == 0.01
    assert ratelimit.RETENTION == timedelta(hours=24)
