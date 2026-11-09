"""S8 pool-api fixtures: the 60-profile pool and the seeded network `ai_usage` rows.

`pool60` inserts 60 trainers straight through the ORM (the trainer self-service API is a
different slice) with deterministic attributes, and returns the PRECOMPUTED id sets that
the filter tests assert against:

    q "needle"        -> i % 10 in {1, 2, 3, 4}   (name / email / headline / bio)   24 ids
    topic python      -> i % 3 == 0                                                 20 ids
    topic kubernetes  -> i % 5 == 0                                                 12 ids
    python ANY k8s    -> i % 3 == 0 or i % 5 == 0                                   28 ids
    verified          -> i % 2 == 0                                                 30 ids
    tag "bengaluru"   -> i % 3 == 1                                                 20 ids

`created_at` is `now - i minutes`, so the pool order (newest first) is i ascending.
Every trainer with i % 6 == 0 has a CV whose `text_extract` holds CV_TEXT_SENTINEL.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.integration.network.admin.pool_seed import (
    HELPDESK_ROWS,
    NETWORK_ROWS,
    POOL_SIZE,
    POOL_TAG,
    RATE_UNITS,
    Pool,
    SpendSeed,
    seed_cv,
    seed_profile,
)



@pytest.fixture
def pool60() -> Pool:
    from src.workshop0.db.session import create_db_session

    now = datetime.now(timezone.utc).replace(microsecond=0)
    pool = Pool(ids=[], user_ids=[], emails=[])
    pool.by_topic = {"python": set(), "kubernetes": set(), "generative-ai": set()}
    pool.by_tag = {POOL_TAG: set(), "mentor": set()}
    with create_db_session() as session:
        for i in range(POOL_SIZE):
            name = f"Trainer {i:02d}"
            email = f"trainer{i:02d}@example.test"
            headline = f"Engineer number {i:02d}"
            bio = "Teaches things to people."
            if i % 10 == 1:
                name = f"Neeedle Needle {i:02d}"  # match via display_name (mixed case)
            elif i % 10 == 2:
                email = f"needle{i:02d}@example.test"  # match via email
            elif i % 10 == 3:
                headline = f"NEEDLE-sharp trainer {i:02d}"  # match via headline
            elif i % 10 == 4:
                bio = f"Finds the needle in the haystack ({i:02d})."  # match via bio
            topics: dict[str, str] = {}
            if i % 3 == 0:
                topics["python"] = "advanced"
            if i % 5 == 0:
                topics["kubernetes"] = "expert"
            if i % 4 == 0:
                topics["generative-ai"] = "intermediate"
            if not topics:
                topics["react"] = "intermediate"
            tags = []
            if i % 3 == 1:
                tags.append(POOL_TAG)
            if i % 7 == 0:
                tags.append("mentor")
            rate = (1000 + i, 2000 + i, "INR", RATE_UNITS[(i // 2) % 4]) if i % 2 else None
            profile = seed_profile(
                session,
                email=email,
                display_name=name,
                headline=headline,
                bio_md=bio,
                created_at=now - timedelta(minutes=i),
                verified=(i % 2 == 0),
                topics=topics,
                tags=tags,
                rate=rate,
                city="Pune" if i % 2 else None,
            )
            pool.ids.append(profile.id)
            pool.user_ids.append(profile.user_id)
            pool.emails.append(email)
            if i % 10 in (1, 2, 3, 4):
                pool.by_q.add(profile.id)
            for slug in topics:
                if slug in pool.by_topic:
                    pool.by_topic[slug].add(profile.id)
            (pool.verified if i % 2 == 0 else pool.unverified).add(profile.id)
            for tag in tags:
                pool.by_tag[tag].add(profile.id)
            if i % 6 == 0:
                cv = seed_cv(session, profile.user_id, storage_key=f"cv/{profile.user_id}/seed.pdf")
                pool.with_cv[profile.id] = cv.id
    assert len(pool.by_q) == 24 and len(pool.verified) == 30 and len(pool.by_tag[POOL_TAG]) == 20
    return pool


@pytest.fixture
def blob_root(tmp_path, monkeypatch):
    """Point the local blob backend at a per-test directory (never the repo's data/)."""
    from src.workshop0.storage import blobstore

    root = tmp_path / "blobs"
    monkeypatch.setenv("WORKSHOP0_BLOB_BACKEND", "local")
    monkeypatch.setattr(blobstore, "DEFAULT_LOCAL_ROOT", root)
    import src.workshop0.config.settings as settings_module

    settings_module._settings = None
    return root


@pytest.fixture
def spend_seed(client, admin_headers) -> SpendSeed:
    """Two trainers with CVs, four network ai_usage rows and two help-desk rows (with a
    workshop_id, which must be excluded from every network figure)."""
    from decimal import Decimal

    from src.workshop0.db.models import AiUsage
    from src.workshop0.db.session import create_db_session
    from tests.conftest import WORKSHOP_BODY

    response = client.post("/api/admin/workshops", json=WORKSHOP_BODY, headers=admin_headers)
    assert response.status_code == 200, response.text
    workshop_id = response.json()["data"]["workshop"]["id"]
    with create_db_session() as session:
        a = seed_profile(session, email="spend-a@example.test", display_name="Spend A", headline="GenAI trainer A")
        b = seed_profile(session, email="spend-b@example.test", display_name="Spend B", headline="GenAI trainer B")
        cv_a = seed_cv(session, a.user_id, storage_key=None, source="text", original_filename=None)
        cv_b = seed_cv(session, b.user_id, storage_key=None, source="text", original_filename=None)
        cv_ids = {"a": cv_a.id, "b": cv_b.id, None: None}
        for purpose, cost, prompt, completion, attach in NETWORK_ROWS:
            session.add(
                AiUsage(
                    workshop_id=None,
                    cv_document_id=cv_ids[attach],
                    purpose=purpose,
                    model="claude-sonnet-5-5",
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    cost_usd=Decimal(cost),
                    latency_ms=900,
                )
            )
        for purpose, cost, prompt, completion in HELPDESK_ROWS:
            # A help-desk row even pointing at trainer A's CV must not count (workshop_id set).
            session.add(
                AiUsage(
                    workshop_id=workshop_id,
                    cv_document_id=cv_a.id,
                    purpose=purpose,
                    model="openrouter/some-model",
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    cost_usd=Decimal(cost),
                    latency_ms=500,
                )
            )
        trainer_a = a.id
    by_purpose: dict[str, tuple[float, int]] = {}
    for purpose, cost, *_ in NETWORK_ROWS:
        prev_cost, prev_count = by_purpose.get(purpose, (Decimal(0), 0))
        by_purpose[purpose] = (prev_cost + Decimal(cost), prev_count + 1)
    return SpendSeed(
        trainer_profile_id=trainer_a,
        trainer_cost=float(Decimal("0.012345") + Decimal("0.000655")),
        total_cost=float(sum(Decimal(r[1]) for r in NETWORK_ROWS)),
        call_count=len(NETWORK_ROWS),
        prompt_tokens=sum(r[2] for r in NETWORK_ROWS),
        completion_tokens=sum(r[3] for r in NETWORK_ROWS),
        by_purpose={k: (float(v[0]), v[1]) for k, v in by_purpose.items()},
    )
