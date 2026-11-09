"""services/ratelimit.py against the production driver (PostgreSQL via TEST_DATABASE_URL).

Covers: the atomic upsert counting, independence of the hit from the caller's transaction,
window rollover, Retry-After correctness, the 24 h opportunistic cleanup, concurrent hits from
two separate engines, and — the Phase-11 gate condition — two separate app instances (each with
its own engine/pool) sharing one database, where the 11th request in an hour is a 429
`rate_limited` with `Retry-After` regardless of which instance serves it.
"""

import threading
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from src.workshop0.db.models import RateLimitHit
from src.workshop0.db.session import create_db_session, get_session
from src.workshop0.services import ratelimit
from src.workshop0.services.ratelimit import RateResult, enforce, hit

T0 = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def no_cleanup(monkeypatch):
    monkeypatch.setattr(ratelimit, "_random", lambda: 0.99)


@pytest.fixture
def engines(test_database_url):
    """Two independent engines (two connection pools) over the same PostgreSQL database."""
    created = [create_engine(test_database_url, pool_size=10) for _ in range(2)]
    yield created
    for engine in created:
        engine.dispose()


def _rows(bucket: str | None = None) -> list[RateLimitHit]:
    with create_db_session() as session:
        stmt = select(RateLimitHit).order_by(RateLimitHit.window_start)
        if bucket is not None:
            stmt = stmt.where(RateLimitHit.bucket == bucket)
        return list(session.execute(stmt).scalars())


# ------------------------------------------------------------------ happy path


def test_hits_are_counted_in_one_row_and_blocked_past_the_limit(no_cleanup):
    with create_db_session() as session:
        now = T0 + timedelta(minutes=20)
        results = [hit(session, "cv:user:7", 10, 3600, now=now) for _ in range(12)]
    assert [r.allowed for r in results] == [True] * 10 + [False] * 2
    assert results[9] == RateResult(allowed=True, retry_after_s=0)
    assert results[10] == RateResult(allowed=False, retry_after_s=40 * 60)

    rows = _rows("cv:user:7")
    assert len(rows) == 1
    assert rows[0].count == 12
    assert rows[0].window_start == T0  # tz-aware UTC round-trip on PostgreSQL


def test_hit_commits_independently_of_the_callers_transaction(no_cleanup):
    """A request that later fails (rollback) still consumed its hit, and holds no row lock."""
    with create_db_session() as session:
        hit(session, "global:draft", 600, 3600, now=T0)
        session.rollback()
    assert _rows("global:draft")[0].count == 1


def test_open_caller_transaction_does_not_block_other_instances(engines, no_cleanup):
    """The upsert's row lock is released at once: a second engine is not blocked by the first
    caller's still-open request transaction (a global bucket must not serialize requests)."""
    first, second = (sessionmaker(bind=e)() for e in engines)
    try:
        assert hit(first, "global:draft", 600, 3600, now=T0).allowed  # first stays open
        done = threading.Event()
        outcome: list[RateResult] = []

        def other() -> None:
            outcome.append(hit(second, "global:draft", 600, 3600, now=T0))
            done.set()

        threading.Thread(target=other, daemon=True).start()
        assert done.wait(timeout=5), "second instance was blocked by the first's transaction"
        assert outcome == [RateResult(True, 0)]
    finally:
        first.close()
        second.close()
    assert _rows("global:draft")[0].count == 2


# ------------------------------------------------------------------ window rollover + Retry-After


def test_window_rollover_resets_the_count(no_cleanup):
    with create_db_session() as session:
        for _ in range(3):
            assert hit(session, "oidc:ip:10.0.0.1", 3, 60, now=T0 + timedelta(seconds=5)).allowed
        blocked = hit(session, "oidc:ip:10.0.0.1", 3, 60, now=T0 + timedelta(seconds=59))
        assert blocked == RateResult(allowed=False, retry_after_s=1)
        assert hit(session, "oidc:ip:10.0.0.1", 3, 60, now=T0 + timedelta(seconds=60)).allowed

    rows = _rows("oidc:ip:10.0.0.1")
    assert [(r.window_start, r.count) for r in rows] == [
        (T0, 4),
        (T0 + timedelta(minutes=1), 1),
    ]


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (timedelta(0), 3600),
        (timedelta(minutes=15), 2700),
        (timedelta(minutes=59, seconds=30), 30),
        (timedelta(minutes=59, seconds=59, milliseconds=500), 1),
    ],
)
def test_retry_after_is_seconds_until_window_end(offset, expected, no_cleanup):
    with create_db_session() as session:
        assert hit(session, "apply:user:3", 1, 3600, now=T0 + offset).allowed
        assert hit(session, "apply:user:3", 1, 3600, now=T0 + offset).retry_after_s == expected


def test_default_now_uses_the_real_clock(no_cleanup):
    with create_db_session() as session:
        hit(session, "clock", 1, 3600)
        blocked = hit(session, "clock", 1, 3600)
    assert not blocked.allowed
    assert 1 <= blocked.retry_after_s <= 3600
    start = _rows("clock")[0].window_start
    assert start <= datetime.now(timezone.utc) < start + timedelta(hours=1)


# ------------------------------------------------------------------ edge + error paths


def test_limit_of_one_and_independent_buckets(no_cleanup):
    with create_db_session() as session:
        assert hit(session, "shortlist:global", 1, 3600, now=T0).allowed
        assert not hit(session, "shortlist:global", 1, 3600, now=T0).allowed
        assert hit(session, "shortlist:other", 1, 3600, now=T0).allowed


def test_invalid_bucket_writes_nothing():
    with create_db_session() as session:
        with pytest.raises(ValueError):
            hit(session, "x" * 121, 10, 3600)
        with pytest.raises(ValueError):
            hit(session, "ok", 0, 3600)
    assert _rows() == []


def test_enforce_raises_429_with_retry_after(no_cleanup):
    with create_db_session() as session:
        enforce(session, "cv:user:9", 1, 3600, now=T0 + timedelta(minutes=30))
        with pytest.raises(Exception) as excinfo:
            enforce(session, "cv:user:9", 1, 3600, now=T0 + timedelta(minutes=30))
    assert excinfo.value.status_code == 429
    assert excinfo.value.detail["code"] == "rate_limited"
    assert excinfo.value.headers == {"Retry-After": "1800"}


def test_cleanup_deletes_rows_older_than_24h(monkeypatch):
    monkeypatch.setattr(ratelimit, "_random", lambda: 0.99)
    with create_db_session() as session:
        hit(session, "stale", 5, 3600, now=T0 - timedelta(hours=26))
        hit(session, "edge", 5, 3600, now=T0 - timedelta(hours=23))
    assert len(_rows()) == 2

    monkeypatch.setattr(ratelimit, "_random", lambda: 0.0)
    with create_db_session() as session:
        hit(session, "fresh", 5, 3600, now=T0)
    assert sorted(r.bucket for r in _rows()) == ["edge", "fresh"]


# ------------------------------------------------------------------ concurrency across engines


def test_concurrent_hits_from_two_engines_are_counted_exactly(engines, no_cleanup):
    limit, per_engine = 7, 15
    results: list[bool] = []
    lock = threading.Lock()
    barrier = threading.Barrier(per_engine * 2)

    def worker(engine) -> None:
        with Session(engine) as session:
            barrier.wait()
            allowed = hit(session, "race", limit, 3600, now=T0).allowed
        with lock:
            results.append(allowed)

    threads = [
        threading.Thread(target=worker, args=(e,)) for e in engines for _ in range(per_engine)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(results) == per_engine * 2
    assert results.count(True) == limit
    with create_db_session() as session:
        total = session.execute(
            select(func.sum(RateLimitHit.count)).where(RateLimitHit.bucket == "race")
        ).scalar_one()
    assert total == per_engine * 2


# ------------------------------------------------------------------ two app instances, one DB


def _instance(make_app, test_database_url):
    """A full create_app() instance whose DB sessions come from its OWN engine (its own pool),
    as two Cloud Run instances would; the probe route enforces the CV-upload limit (10/h/user)."""
    app = make_app()
    engine = create_engine(test_database_url, pool_size=5)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def own_session() -> Generator[Session, None, None]:
        with factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    @app.post("/__test/ratelimit/{user_id}")
    def probe(user_id: int, session: Session = Depends(get_session)) -> dict:
        enforce(session, f"cv:user:{user_id}", 10, 3600)
        return {"data": {"ok": True}, "error": None}

    app.dependency_overrides[get_session] = own_session
    return TestClient(app), engine


def test_limit_holds_across_two_app_instances_sharing_the_db(
    make_app, test_database_url, no_cleanup
):
    (client_a, engine_a), (client_b, engine_b) = (
        _instance(make_app, test_database_url),
        _instance(make_app, test_database_url),
    )
    try:
        assert engine_a is not engine_b
        statuses = []
        for i in range(10):  # alternate instances: 5 + 5 allowed uploads
            client = client_a if i % 2 == 0 else client_b
            statuses.append(client.post("/__test/ratelimit/42").status_code)
        assert statuses == [200] * 10

        for client in (client_a, client_b):  # the 11th (and 12th) on EITHER instance → 429
            response = client.post("/__test/ratelimit/42")
            assert response.status_code == 429
            assert response.json() == {
                "detail": {"code": "rate_limited", "message": response.json()["detail"]["message"]}
            }
            assert response.json()["detail"]["message"].startswith("Too many requests")
            retry_after = int(response.headers["Retry-After"])
            assert 1 <= retry_after <= 3600

        assert client_b.post("/__test/ratelimit/43").status_code == 200  # other user unaffected
    finally:
        engine_a.dispose()
        engine_b.dispose()

    rows = _rows("cv:user:42")
    assert len(rows) == 1 and rows[0].count == 12
