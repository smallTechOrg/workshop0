"""The 0001_initial migration creates the FULL v0.2 schema on a fresh DB and
`alembic current` reports a non-blank revision."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_TABLES = {
    "workshop",
    "milestone",
    "participant",
    "milestone_completion",
    "help_request",
    "help_answer",
    "broadcast",
    "facilitator_action",
    "agenda_template",
    "agenda_template_milestone",
    "join_form_template",
    "ai_usage",
    # Phase 10 — 0005_opportunity_board
    "topic",
    "opportunity",
    "opportunity_topic",
    # Phase 11 — 0006_trainer_network
    "app_user",
    "auth_session",
    "rate_limit_hit",
    "trainer_profile",
    "trainer_topic",
    "cv_document",
    "network_invite",
    "trainer_tag",
    "admin_note",
    # Phase 11b — 0007_partners_compensation
    "partner",
    "alembic_version",
}
BOARD_TABLES = {"topic", "opportunity", "opportunity_topic"}
NETWORK_TABLES = {
    "app_user",
    "auth_session",
    "rate_limit_hit",
    "trainer_profile",
    "trainer_topic",
    "cv_document",
    "network_invite",
    "trainer_tag",
    "admin_note",
}
PARTNER_TABLES = {"partner"}
AI_USAGE_NETWORK_COLUMNS = {"cv_document_id", "opportunity_id"}
AUDIT_SUBJECT_COLUMNS = {"subject_type", "subject_id"}
SEED_CATEGORIES = {"Languages", "Web & Mobile", "AI & Data", "Cloud & DevOps", "Engineering Practice"}


def _alembic_config() -> Config:
    return Config(str(REPO_ROOT / "alembic.ini"))


def _use(monkeypatch, url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", url)
    import src.workshop0.config.settings as settings_module
    from src.workshop0.db.session import reset_db_state

    settings_module._settings = None
    reset_db_state()


def test_upgrade_head_creates_full_schema_and_stamps_revision(monkeypatch, scratch_database):
    url = scratch_database()
    _use(monkeypatch, url)

    config = _alembic_config()
    command.upgrade(config, "head")

    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == EXPECTED_TABLES

        # help_corpus (Phase-4 FTS5) is NOT created by 0001_initial
        assert "help_corpus" not in inspector.get_table_names()

        # unique constraints that make the API idempotent/secure
        workshop_indexes = {idx["name"]: idx for idx in inspector.get_indexes("workshop")}
        assert workshop_indexes["ix_workshop_admin_token"]["unique"]
        assert workshop_indexes["ix_workshop_join_slug"]["unique"]
        completion_uniques = inspector.get_unique_constraints("milestone_completion")
        assert any(
            set(uc["column_names"]) == {"participant_id", "milestone_id"}
            for uc in completion_uniques
        )

        # the stamped revision matches the script head (what `alembic current` prints)
        with engine.connect() as connection:
            stamped = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        head = ScriptDirectory.from_config(config).get_current_head()
        assert stamped == head
        assert stamped  # non-blank
    finally:
        engine.dispose()


def test_upgrade_head_twice_is_a_noop(monkeypatch, scratch_database):
    url = scratch_database()
    _use(monkeypatch, url)
    config = _alembic_config()
    command.upgrade(config, "head")

    engine = create_engine(url)
    try:
        before = inspect(engine).get_table_names()
        command.upgrade(config, "head")
        assert inspect(engine).get_table_names() == before
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT version_num FROM alembic_version")).all()
        assert [r[0] for r in rows] == [ScriptDirectory.from_config(config).get_current_head()]
    finally:
        engine.dispose()


def test_downgrade_base_then_upgrade_head_round_trips(monkeypatch, scratch_database):
    url = scratch_database()
    _use(monkeypatch, url)
    config = _alembic_config()
    command.upgrade(config, "head")

    engine = create_engine(url)
    try:
        command.downgrade(config, "base")
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
        command.upgrade(config, "head")
        assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES
    finally:
        engine.dispose()


def test_migrated_schema_serves_the_api(monkeypatch, scratch_database):
    """App over a freshly alembic-migrated scratch DB serves the core loop."""
    _use(monkeypatch, scratch_database())

    command.upgrade(_alembic_config(), "head")

    from fastapi.testclient import TestClient

    from src.workshop0.api import create_app
    from tests.conftest import TEST_ADMIN_KEY, WORKSHOP_BODY

    client = TestClient(create_app())
    workshop = client.post(
        "/api/admin/workshops", json=WORKSHOP_BODY, headers={"X-Admin-Key": TEST_ADMIN_KEY}
    ).json()["data"]["workshop"]
    joined = client.post(
        f"/api/join/{workshop['join_slug']}", json={"name": "Priya"}
    ).json()["data"]
    state = client.get(f"/api/p/{joined['participant_token']}/state").json()["data"]
    assert state["me"]["name"] == "Priya"
    assert state["me"]["total_count"] == 3


def _topic_seed(engine) -> list[tuple]:
    with engine.connect() as connection:
        return [
            tuple(r)
            for r in connection.execute(
                text("SELECT slug, name, category, position, active FROM topic ORDER BY position")
            )
        ]


def _assert_seed(rows: list[tuple]) -> None:
    assert len(rows) == 40
    assert [r[3] for r in rows] == list(range(40))
    assert all(r[4] is True for r in rows)
    assert len({r[0] for r in rows}) == 40 and len({r[1] for r in rows}) == 40
    by_category: dict[str, int] = {}
    for r in rows:
        by_category[r[2]] = by_category.get(r[2], 0) + 1
    assert by_category == {c: 8 for c in SEED_CATEGORIES}
    assert rows[0][:3] == ("python", "Python", "Languages")
    assert rows[6][:2] == ("dotnet", "C# / .NET")
    assert rows[18][:2] == ("generative-ai", "Generative AI & LLMs")
    assert rows[39][:3] == ("ux-design", "UI / UX Design", "Engineering Practice")


def test_0005_seeds_topics_and_downgrade_to_0004_removes_the_board(monkeypatch, scratch_database):
    url = scratch_database()
    _use(monkeypatch, url)
    config = _alembic_config()
    command.upgrade(config, "head")

    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        _assert_seed(_topic_seed(engine))
        assert AUDIT_SUBJECT_COLUMNS <= {c["name"] for c in inspector.get_columns("facilitator_action")}
        audit_indexes = {i["name"]: i["column_names"] for i in inspector.get_indexes("facilitator_action")}
        assert audit_indexes["ix_facilitator_action_subject_created"] == [
            "subject_type", "subject_id", "created_at"
        ]
        assert {"ix_opportunity_status_deadline", "ix_opportunity_published_at"} <= {
            i["name"] for i in inspector.get_indexes("opportunity")
        }
        topic_fk = [fk for fk in inspector.get_foreign_keys("opportunity_topic") if fk["referred_table"] == "topic"]
        assert topic_fk and topic_fk[0]["options"].get("ondelete") in (None, "RESTRICT")

        command.downgrade(config, "0004")
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == EXPECTED_TABLES - BOARD_TABLES - NETWORK_TABLES - PARTNER_TABLES
        assert not AUDIT_SUBJECT_COLUMNS & {c["name"] for c in inspector.get_columns("facilitator_action")}
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0004"

        command.upgrade(config, "head")
        assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES
        _assert_seed(_topic_seed(engine))  # re-seeded exactly once, not duplicated
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0008"
    finally:
        engine.dispose()


def test_0005_upgrade_keeps_pre_existing_audit_rows_with_null_subject(monkeypatch, scratch_database):
    url = scratch_database()
    _use(monkeypatch, url)
    config = _alembic_config()
    command.upgrade(config, "0004")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO workshop (name, description_md, admin_token, join_slug, status, grace_hours,"
                " paused, state_version, content_version, ai_enabled, join_form_json, stuck_minutes,"
                " created_at, updated_at) VALUES ('W', '', 'tok', 'slug', 'live', 24, false, 0, 0, false,"
                " '[]', 10, now(), now())"
            ))
            connection.execute(text(
                "INSERT INTO facilitator_action (workshop_id, actor, action, detail_json, created_at)"
                " SELECT id, 'facilitator', 'workshop.create', '{}', now() FROM workshop"
            ))
        command.upgrade(config, "head")
        with engine.connect() as connection:
            row = connection.execute(text(
                "SELECT actor, subject_type, subject_id FROM facilitator_action"
            )).one()
        assert tuple(row) == ("facilitator", None, None)
    finally:
        engine.dispose()


# --------------------------------------------------------------------------- Phase 11 — 0006


def _version(engine) -> str:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()


def _columns(inspector, table: str) -> dict[str, dict]:
    return {c["name"]: c for c in inspector.get_columns(table)}


def _fks(inspector, table: str) -> dict[str, dict]:
    return {fk["constrained_columns"][0]: fk for fk in inspector.get_foreign_keys(table)}


def test_0006_creates_the_network_schema_and_0007_is_head_and_creates_the_network_schema(monkeypatch, scratch_database):
    url = scratch_database()
    _use(monkeypatch, url)
    config = _alembic_config()
    assert ScriptDirectory.from_config(config).get_current_head() == "0008"
    command.upgrade(config, "0006")

    engine = create_engine(url)
    try:
        assert _version(engine) == "0006"
        inspector = inspect(engine)
        assert NETWORK_TABLES <= set(inspector.get_table_names())

        # app_user: unique email + unique (issuer, subject); no role column
        user_cols = _columns(inspector, "app_user")
        assert "role" not in user_cols and "is_admin" not in user_cols
        assert user_cols["oidc_issuer"]["nullable"] and user_cols["oidc_subject"]["nullable"]
        user_uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints("app_user")}
        assert ("email",) in user_uniques and ("oidc_issuer", "oidc_subject") in user_uniques

        # auth_session: hashed token unique, user FK cascades, indexed
        assert ("token_hash",) in {
            tuple(u["column_names"]) for u in inspector.get_unique_constraints("auth_session")
        }
        assert _columns(inspector, "auth_session")["token_hash"]["type"].length == 64
        assert _fks(inspector, "auth_session")["user_id"]["options"]["ondelete"] == "CASCADE"
        assert ["user_id"] in [i["column_names"] for i in inspector.get_indexes("auth_session")]

        # rate_limit_hit composite PK
        assert inspector.get_pk_constraint("rate_limit_hit")["constrained_columns"] == [
            "bucket", "window_start"
        ]

        # 1:1 profile / CV per user
        for table in ("trainer_profile", "cv_document"):
            assert ("user_id",) in {tuple(u["column_names"]) for u in inspector.get_unique_constraints(table)}
            assert _fks(inspector, table)["user_id"]["options"]["ondelete"] == "CASCADE"
        profile_cols = _columns(inspector, "trainer_profile")
        assert not profile_cols["consent_at"]["nullable"]
        assert not profile_cols["consent_version"]["nullable"]

        assert inspector.get_pk_constraint("trainer_topic")["constrained_columns"] == ["profile_id", "topic_id"]
        assert inspector.get_pk_constraint("trainer_tag")["constrained_columns"] == ["profile_id", "tag"]
        assert ("token",) in {
            tuple(u["column_names"]) for u in inspector.get_unique_constraints("network_invite")
        }
        assert _fks(inspector, "network_invite")["accepted_user_id"]["options"]["ondelete"] == "SET NULL"
        assert _fks(inspector, "admin_note")["profile_id"]["options"]["ondelete"] == "CASCADE"

        # ai_usage changes
        ai_cols = _columns(inspector, "ai_usage")
        assert ai_cols["workshop_id"]["nullable"]
        assert AI_USAGE_NETWORK_COLUMNS <= set(ai_cols)
        ai_fks = _fks(inspector, "ai_usage")
        assert ai_fks["cv_document_id"]["referred_table"] == "cv_document"
        assert ai_fks["opportunity_id"]["referred_table"] == "opportunity"
        assert ai_fks["cv_document_id"]["options"]["ondelete"] == "SET NULL"
        assert ai_fks["opportunity_id"]["options"]["ondelete"] == "SET NULL"
    finally:
        engine.dispose()


def _seed_network(connection) -> None:
    """One user + session + profile + CV + a network ai_usage row (workshop_id NULL)."""
    connection.execute(text(
        "INSERT INTO app_user (email, email_verified, display_name, created_at)"
        " VALUES ('t@example.test', true, 't', now())"
    ))
    connection.execute(text(
        "INSERT INTO auth_session (token_hash, user_id, created_at, expires_at, last_seen_at)"
        " SELECT repeat('a', 64), id, now(), now() + interval '30 days', now() FROM app_user"
    ))
    connection.execute(text(
        "INSERT INTO trainer_profile (user_id, headline, consent_at, consent_version, created_at,"
        " updated_at) SELECT id, 'GenAI trainer', now(), '2026-11', now(), now() FROM app_user"
    ))
    connection.execute(text(
        "INSERT INTO cv_document (user_id, source, sha256, created_at)"
        " SELECT id, 'text', repeat('b', 64), now() FROM app_user"
    ))
    connection.execute(text(
        "INSERT INTO ai_usage (workshop_id, cv_document_id, purpose, model, prompt_tokens,"
        " completion_tokens, cost_usd, latency_ms, created_at)"
        " SELECT NULL, id, 'profile_draft', 'claude-sonnet-5-5', 100, 50, 0.001, 10, now()"
        " FROM cv_document"
    ))


def test_0006_defaults_and_cascades_hold_on_real_rows(monkeypatch, scratch_database):
    url = scratch_database()
    _use(monkeypatch, url)
    command.upgrade(_alembic_config(), "head")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            _seed_network(connection)
        with engine.connect() as connection:
            profile = connection.execute(text(
                "SELECT bio_md, remote_ok, pro_bono, past_work_json, availability_json,"
                " blackout_json, visibility, verified, autofilled_fields_json FROM trainer_profile"
            )).one()
            assert tuple(profile) == ("", True, False, "[]", "{}", "[]", "private", False, "[]")
            assert connection.execute(text("SELECT draft_status FROM cv_document")).scalar() == "pending"
        with engine.begin() as connection:
            # deleting the CV keeps the spend row (SET NULL); deleting the user cascades the rest
            connection.execute(text("DELETE FROM cv_document"))
            assert connection.execute(text("SELECT cv_document_id FROM ai_usage")).scalar() is None
            connection.execute(text("DELETE FROM app_user"))
        with engine.connect() as connection:
            for table in ("auth_session", "trainer_profile"):
                assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0
            assert connection.execute(text("SELECT count(*) FROM ai_usage")).scalar() == 1
    finally:
        engine.dispose()


def test_0006_downgrade_to_0005_and_back_round_trips(monkeypatch, scratch_database):
    url = scratch_database()
    _use(monkeypatch, url)
    config = _alembic_config()
    command.upgrade(config, "head")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            _seed_network(connection)

        command.downgrade(config, "0005")
        inspector = inspect(engine)
        assert _version(engine) == "0005"
        assert set(inspector.get_table_names()) == EXPECTED_TABLES - NETWORK_TABLES - PARTNER_TABLES
        ai_cols = _columns(inspector, "ai_usage")
        assert not AI_USAGE_NETWORK_COLUMNS & set(ai_cols)
        assert not ai_cols["workshop_id"]["nullable"]
        with engine.connect() as connection:  # network rows cannot survive NOT NULL
            assert connection.execute(text("SELECT count(*) FROM ai_usage")).scalar() == 0
        _assert_seed(_topic_seed(engine))  # Phase-10 data untouched

        command.upgrade(config, "head")
        assert _version(engine) == "0008"
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == EXPECTED_TABLES
        assert _columns(inspector, "ai_usage")["workshop_id"]["nullable"]
    finally:
        engine.dispose()


def test_0006_upgrade_keeps_existing_help_desk_ai_usage_rows(monkeypatch, scratch_database):
    url = scratch_database()
    _use(monkeypatch, url)
    config = _alembic_config()
    command.upgrade(config, "0005")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO workshop (name, description_md, admin_token, join_slug, status, grace_hours,"
                " paused, state_version, content_version, ai_enabled, join_form_json, stuck_minutes,"
                " created_at, updated_at) VALUES ('W', '', 'tok', 'slug', 'live', 24, false, 0, 0, true,"
                " '[]', 10, now(), now())"
            ))
            connection.execute(text(
                "INSERT INTO ai_usage (workshop_id, purpose, model, prompt_tokens, completion_tokens,"
                " cost_usd, latency_ms, created_at) SELECT id, 'triage_answer', 'm', 1, 1, 0.5, 1, now()"
                " FROM workshop"
            ))
        command.upgrade(config, "head")
        with engine.connect() as connection:
            row = connection.execute(text(
                "SELECT purpose, cost_usd, cv_document_id, opportunity_id FROM ai_usage"
            )).one()
        assert (row[0], float(row[1]), row[2], row[3]) == ("triage_answer", 0.5, None, None)
    finally:
        engine.dispose()


# --------------------------------------------------------------------------- Phase 11b — 0007

_OPP_INSERT = (
    "INSERT INTO opportunity (title, type, summary, description_md, location_mode, deadline,"
    " partner_display_name, partner_internal_name, status, created_at, updated_at)"
    " VALUES (:t, 'trainer', 's', '', 'remote', now(), :d, :n, 'draft', now(), :u)"
)


def _seed_pre_0007(engine) -> None:
    rows = [
        ("a1", "Acme  Corp", "A fintech", "2026-01-01T00:00:00+00:00"),
        ("a2", "acme corp", "A fintech", "2026-03-01T00:00:00+00:00"),
        ("a3", " ACME CORP ", "An Acme", "2026-02-01T00:00:00+00:00"),
        ("b1", "Beta Ltd", None, "2026-01-01T00:00:00+00:00"),
        ("n1", None, "x", "2026-01-01T00:00:00+00:00"),
        ("n2", "   ", "x", "2026-01-01T00:00:00+00:00"),
    ]
    with engine.begin() as connection:
        for t, n, d, u in rows:
            connection.execute(text(_OPP_INSERT), {"t": t, "n": n, "d": d, "u": u})


def test_0007_schema_and_widened_purpose(monkeypatch, scratch_database):
    url = scratch_database()
    _use(monkeypatch, url)
    config = _alembic_config()
    command.upgrade(config, "head")
    engine = create_engine(url)
    try:
        assert _version(engine) == "0008"
        inspector = inspect(engine)
        pcols = _columns(inspector, "partner")
        assert set(pcols) == {
            "id", "internal_name", "name_key", "display_name", "notes", "active", "created_at", "updated_at"
        }
        assert not pcols["name_key"]["nullable"] and not pcols["internal_name"]["nullable"]
        assert any(
            u["column_names"] == ["name_key"] for u in inspector.get_unique_constraints("partner")
        )
        ocols = _columns(inspector, "opportunity")
        assert {"partner_id", "compensation_min", "compensation_max", "compensation_currency",
                "compensation_unit", "compensation_text", "partner_internal_name"} <= set(ocols)
        assert ocols["partner_id"]["nullable"]
        assert _fks(inspector, "opportunity")["partner_id"]["referred_table"] == "partner"
        assert _fks(inspector, "opportunity")["partner_id"]["options"].get("ondelete") == "RESTRICT"
        assert "ix_opportunity_partner_id" in {i["name"] for i in inspector.get_indexes("opportunity")}
        assert ocols["compensation_currency"]["type"].length == 3
        assert ocols["compensation_unit"]["type"].length == 8
        assert _columns(inspector, "ai_usage")["purpose"]["type"].length == 32
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO ai_usage (workshop_id, purpose, model, prompt_tokens, completion_tokens,"
                " cost_usd, latency_ms, created_at)"
                " VALUES (NULL, 'opportunity_draft', 'claude-sonnet-5-5', 1, 1, 0, 1, now())"
            ))
            # RESTRICT: a referenced partner cannot be deleted; name_key is unique
            connection.execute(text(
                "INSERT INTO partner (internal_name, name_key, active, created_at, updated_at)"
                " VALUES ('P', 'p', true, now(), now())"
            ))
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO partner (internal_name, name_key, created_at, updated_at)"
                " VALUES ('p', 'p', now(), now())"
            ))
    finally:
        engine.dispose()


def test_0007_data_migration_merges_free_text_partners(monkeypatch, scratch_database):
    url = scratch_database()
    _use(monkeypatch, url)
    config = _alembic_config()
    command.upgrade(config, "0006")
    engine = create_engine(url)
    try:
        _seed_pre_0007(engine)
        command.upgrade(config, "head")
        with engine.connect() as connection:
            partners = connection.execute(text(
                "SELECT id, internal_name, name_key, display_name, notes, active FROM partner ORDER BY name_key"
            )).all()
            assert [(p[1], p[2], p[3], p[4], p[5]) for p in partners] == [
                ("acme corp", "acme corp", "A fintech", None, True),  # latest (a2) spelling, most common public name
                ("Beta Ltd", "beta ltd", None, None, True),
            ]
            links = dict(connection.execute(text("SELECT title, partner_id FROM opportunity")).all())
        acme, beta = partners[0][0], partners[1][0]
        assert links == {"a1": acme, "a2": acme, "a3": acme, "b1": beta, "n1": None, "n2": None}
        with engine.connect() as connection:  # mirror untouched
            mirror = connection.execute(text(
                "SELECT partner_internal_name FROM opportunity WHERE title='a1'"
            )).scalar()
        assert mirror == "Acme  Corp"
    finally:
        engine.dispose()


def test_0007_downgrade_restores_mirror_compensation_and_round_trips(monkeypatch, scratch_database):
    url = scratch_database()
    _use(monkeypatch, url)
    config = _alembic_config()
    command.upgrade(config, "0006")
    engine = create_engine(url)
    try:
        _seed_pre_0007(engine)
        command.upgrade(config, "head")
        with engine.begin() as connection:
            connection.execute(text(
                "UPDATE opportunity SET compensation_min=5000, compensation_max=8000,"
                " compensation_currency='INR', compensation_unit='day' WHERE title='a1'"
            ))
            connection.execute(text(
                "UPDATE opportunity SET compensation_min=100, compensation_currency='USD',"
                " compensation_unit='hour', compensation_text='note' WHERE title='b1'"
            ))
            connection.execute(text(
                "UPDATE opportunity SET compensation_max=9, compensation_currency='USD',"
                " compensation_unit='month' WHERE title='a2'"
            ))
            connection.execute(text(
                "UPDATE opportunity SET partner_internal_name='stale' WHERE title='a3'"
            ))
            connection.execute(text(
                "INSERT INTO ai_usage (workshop_id, purpose, model, prompt_tokens, completion_tokens,"
                " cost_usd, latency_ms, created_at) VALUES"
                " (NULL, 'opportunity_draft', 'm', 1, 1, 0, 1, now()),"
                " (NULL, 'profile_draft', 'm', 1, 1, 0, 1, now())"
            ))

        command.downgrade(config, "0006")
        inspector = inspect(engine)
        assert _version(engine) == "0006"
        assert "partner" not in inspector.get_table_names()
        assert not {"partner_id", "compensation_min", "compensation_max", "compensation_currency",
                    "compensation_unit"} & set(_columns(inspector, "opportunity"))
        assert _columns(inspector, "ai_usage")["purpose"]["type"].length == 16
        with engine.connect() as connection:
            opp = {r[0]: (r[1], r[2]) for r in connection.execute(text(
                "SELECT title, partner_internal_name, compensation_text FROM opportunity"
            ))}
            purposes = [r[0] for r in connection.execute(text("SELECT purpose FROM ai_usage"))]
        assert opp["a1"] == ("acme corp", "INR 5000-8000 / day")
        assert opp["a3"][0] == "acme corp"  # mirror rewritten from the partner
        assert opp["b1"] == ("Beta Ltd", "note")  # existing note kept
        assert opp["a2"][1] == "USD 9 / month"
        assert opp["n1"] == (None, None)
        assert purposes == ["profile_draft"]  # >16-char purposes removed

        command.upgrade(config, "head")
        assert _version(engine) == "0008"
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM partner")).scalar() == 2
    finally:
        engine.dispose()


# --------------------------------------------------------------------------- Phase 11c — 0008

_OPP_LOC_INSERT = (
    "INSERT INTO opportunity (title, type, summary, description_md, location_mode, city, deadline,"
    " status, created_at, updated_at)"
    " VALUES (:t, 'trainer', 's', '', :m, :c, now(), 'draft', now(), now())"
)

_PRE_0008 = [
    ("pune", "onsite", "Pune"),
    ("navi", "hybrid", "  Navi   Mumbai "),
    ("remote", "remote", None),
    ("blank", "onsite", "   "),
    ("zurich", "hybrid", "Zürich"),
]


def _seed_pre_0008(engine) -> None:
    with engine.begin() as connection:
        for t, m, c in _PRE_0008:
            connection.execute(text(_OPP_LOC_INSERT), {"t": t, "m": m, "c": c})


def _locations(engine) -> dict[str, tuple]:
    import json

    with engine.connect() as connection:
        return {
            r[0]: (json.loads(r[1]), r[2])
            for r in connection.execute(text("SELECT title, locations_json, city FROM opportunity"))
        }


def test_0008_upgrade_migrates_single_city_to_locations(monkeypatch, scratch_database):
    url = scratch_database()
    _use(monkeypatch, url)
    config = _alembic_config()
    command.upgrade(config, "0007")
    engine = create_engine(url)
    try:
        _seed_pre_0008(engine)
        command.upgrade(config, "head")
        assert _version(engine) == "0008"
        assert ScriptDirectory.from_config(config).get_current_head() == "0008"
        col = _columns(inspect(engine), "opportunity")["locations_json"]
        assert not col["nullable"]
        got = _locations(engine)
        assert got == {
            "pune": ([{"city": "Pune", "country": None}], "Pune"),
            "navi": ([{"city": "Navi Mumbai", "country": None}], "  Navi   Mumbai "),
            "remote": ([], None),
            "blank": ([], "   "),
            "zurich": ([{"city": "Zürich", "country": None}], "Zürich"),
        }
        with engine.begin() as connection:  # server_default applies to new rows
            connection.execute(text(_OPP_LOC_INSERT), {"t": "new", "m": "remote", "c": None})
        assert _locations(engine)["new"] == ([], None)
    finally:
        engine.dispose()


def test_0008_downgrade_restores_first_city_and_round_trips(monkeypatch, scratch_database):
    import json

    url = scratch_database()
    _use(monkeypatch, url)
    config = _alembic_config()
    command.upgrade(config, "0007")
    engine = create_engine(url)
    try:
        _seed_pre_0008(engine)
        command.upgrade(config, "head")
        many = json.dumps(
            [{"city": c, "country": None} for c in ("Bengaluru", "Pune", "Hyderabad")], ensure_ascii=False
        )
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE opportunity SET locations_json = :v, city = 'Stale' WHERE title = 'pune'"),
                {"v": many},
            )
        command.downgrade(config, "0007")
        assert _version(engine) == "0007"
        assert "locations_json" not in _columns(inspect(engine), "opportunity")
        with engine.connect() as connection:
            cities = dict(connection.execute(text("SELECT title, city FROM opportunity")).all())
        assert cities == {
            "pune": "Bengaluru",
            "navi": "Navi Mumbai",  # mirror rewritten from the collapsed first location
            "remote": None,
            "blank": "   ",
            "zurich": "Zürich",
        }

        command.upgrade(config, "head")
        assert _version(engine) == "0008"
        got = _locations(engine)
        assert got["pune"] == ([{"city": "Bengaluru", "country": None}], "Bengaluru")
        assert got["zurich"] == ([{"city": "Zürich", "country": None}], "Zürich")
        assert got["remote"] == ([], None)
    finally:
        engine.dispose()
