"""Admin pool list / CSV must not issue per-row queries (no N+1 on topic counts or CV
presence for completeness). Counts SQL statements on 3 vs 15 profiles (PostgreSQL)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import event

from tests.integration.network.admin.pool_seed import seed_cv, seed_profile


def _seed(n: int) -> list[int]:
    from src.workshop0.db.session import create_db_session

    now = datetime.now(timezone.utc).replace(microsecond=0)
    ids: list[int] = []
    with create_db_session() as session:
        for i in range(n):
            profile = seed_profile(
                session,
                email=f"qc{n}-{i:02d}@example.test",
                display_name=f"QC Trainer {i:02d}",
                headline=f"Engineer {i:02d}",
                created_at=now - timedelta(minutes=i),
                topics={"python": "expert", "kubernetes": "intermediate", "generative-ai": "beginner"}
                if i % 2 == 0
                else {"python": "beginner"},
                tags=["mentor"],
            )
            if i % 3 == 0:
                seed_cv(session, profile.user_id, storage_key=None)
            ids.append(profile.id)
        session.commit()
    return ids


@contextmanager
def _count_queries():
    from src.workshop0.db.session import get_engine

    counter = {"n": 0}

    def _on_execute(*_args, **_kwargs):
        counter["n"] += 1

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", _on_execute)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _on_execute)


def _list(client, admin_headers) -> tuple[int, dict]:
    with _count_queries() as counter:
        response = client.get(
            "/api/admin/network/trainers", params={"page_size": "50"}, headers=admin_headers
        )
    assert response.status_code == 200, response.text
    return counter["n"], response.json()["data"]


def _csv(client, admin_headers) -> int:
    with _count_queries() as counter:
        response = client.get("/api/admin/network/trainers.csv", headers=admin_headers)
    assert response.status_code == 200, response.text
    return counter["n"]


def test_pool_list_query_count_is_constant_in_profile_count(client, admin_headers):
    _seed(3)
    small, small_data = _list(client, admin_headers)
    assert small_data["total"] == 3
    _seed(12)
    large, large_data = _list(client, admin_headers)
    assert large_data["total"] == 15
    assert large == small, f"pool list issued {small} queries for 3 rows but {large} for 15"
    # completeness still reflects batched topic counts + CV presence
    pcts = {row["display_name"]: row["completeness_pct"] for row in large_data["trainers"]}
    assert len(set(pcts.values())) > 1


def test_pool_csv_query_count_is_constant_in_profile_count(client, admin_headers):
    _seed(3)
    small = _csv(client, admin_headers)
    _seed(12)
    large = _csv(client, admin_headers)
    assert large == small, f"CSV export issued {small} queries for 3 rows but {large} for 15"


def test_completeness_matches_unbatched_computation(client, admin_headers):
    from sqlalchemy import select

    from src.workshop0.db.models import TrainerProfile
    from src.workshop0.db.session import create_db_session
    from src.workshop0.services import profiles

    ids = _seed(6)
    _, data = _list(client, admin_headers)
    got = {row["id"]: row["completeness_pct"] for row in data["trainers"]}
    with create_db_session() as session:
        for profile in session.scalars(select(TrainerProfile).where(TrainerProfile.id.in_(ids))):
            assert got[profile.id] == profiles.completeness(profile).pct
