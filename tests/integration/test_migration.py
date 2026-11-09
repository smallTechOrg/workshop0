"""The 0001_initial migration creates the FULL v0.2 schema on a fresh DB and
`alembic current` reports a non-blank revision."""

from pathlib import Path

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
    "alembic_version",
}
BOARD_TABLES = {"topic", "opportunity", "opportunity_topic"}
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
        assert set(inspector.get_table_names()) == EXPECTED_TABLES - BOARD_TABLES
        assert not AUDIT_SUBJECT_COLUMNS & {c["name"] for c in inspector.get_columns("facilitator_action")}
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0004"

        command.upgrade(config, "head")
        assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES
        _assert_seed(_topic_seed(engine))  # re-seeded exactly once, not duplicated
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0005"
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
