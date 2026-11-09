"""SQLite -> PostgreSQL import (scripts/sqlite_to_postgres.py), against real PostgreSQL.

The source is a fixture database built through the real app (scripts/make_import_fixture.py:
3 workshops, 320+ participants, ~980 completions — more rows than one 500-row batch).
Covers: per-table counts, API parity over source vs imported DB, sequence reset,
refusal paths that change nothing, all-or-nothing atomicity, idempotent --replace,
robust datetime/bool parsing, read-only source, and the CLI + log output.
"""

import hashlib
import importlib.util
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.conftest import alembic_upgrade

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


imp = _load("sqlite_to_postgres")

APP_TABLES = [t.name for t in imp.Base.metadata.sorted_tables]
ID_TABLES = [t.name for t in imp.Base.metadata.sorted_tables if "id" in t.c]
SEEDED_TOPICS = 40  # alembic 0005 seed: present in every migrated target before any import


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(scope="module")
def fixture_db(tmp_path_factory) -> Path:
    """Built once, in a clean subprocess (so env/settings of this process are untouched)."""
    path = tmp_path_factory.mktemp("import-fixture") / "fixture.db"
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "make_import_fixture.py"), "--out", str(path)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return path


@pytest.fixture
def source(fixture_db, tmp_path) -> Path:
    """A private mutable copy of the fixture (tests that damage the source use this)."""
    dest = tmp_path / "source.db"
    src = sqlite3.connect(fixture_db)
    out = sqlite3.connect(dest)
    src.backup(out)
    src.close()
    out.close()
    return dest


@pytest.fixture
def target(scratch_database) -> str:
    """Empty, fully migrated PostgreSQL database (same server as the suite)."""
    url = scratch_database()
    alembic_upgrade(url)
    return url


def _sqlite_counts(path: Path) -> dict[str, int]:
    conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    try:
        return {t: conn.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in APP_TABLES}
    finally:
        conn.close()


def _pg_counts(url: str) -> dict[str, int]:
    engine = create_engine(url)
    try:
        with engine.connect() as c:
            return {t: c.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one() for t in APP_TABLES}
    finally:
        engine.dispose()


def _pg_scalar(url: str, sql: str, **params):
    engine = create_engine(url)
    try:
        with engine.connect() as c:
            return c.execute(text(sql), params).scalar()
    finally:
        engine.dispose()


def _assert_target_untouched(url: str) -> None:
    """A migrated target nobody imported into: app tables empty, only the topic seed."""
    counts = _pg_counts(url)
    assert {t: n for t, n in counts.items() if t not in imp.REFERENCE_TABLES} == {
        t: 0 for t in APP_TABLES if t not in imp.REFERENCE_TABLES
    }
    assert counts["topic"] == SEEDED_TOPICS


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(source: Path, url: str, capsys=None, **kwargs) -> int:
    return imp.run_import(source, url, **kwargs)


# --------------------------------------------------------------------------- happy path


def test_counts_equal_per_table_tokens_survive_and_no_row_data_printed(source, target, capsys):
    before_sha = _sha(source)
    expected = _sqlite_counts(source)
    assert expected["participant"] >= 300 and expected["milestone_completion"] >= 900
    assert expected["participant"] + expected["milestone_completion"] > 500 * 2  # > one batch

    assert _run(source, target) == imp.EXIT_OK
    out = capsys.readouterr().out

    assert _pg_counts(target) == expected
    for table in APP_TABLES:
        assert any(line.startswith(table) and line.rstrip().endswith("OK") for line in out.splitlines()), table
    assert "TOTAL" in out and "MISMATCH" not in out
    # PII: no participant names, tokens or message text in the log.
    assert "Person 0" not in out and "stuck on thing" not in out and "Welcome!" not in out
    sconn = sqlite3.connect(f"file:{source}?mode=ro&immutable=1", uri=True)
    tokens = [r[0] for r in sconn.execute("SELECT token FROM participant ORDER BY id LIMIT 5")]
    admin_token = sconn.execute("SELECT admin_token FROM workshop ORDER BY id LIMIT 1").fetchone()[0]
    sconn.close()
    assert all(tok not in out for tok in tokens) and admin_token not in out
    # tokens survive byte-for-byte
    for tok in tokens:
        assert _pg_scalar(target, "SELECT count(*) FROM participant WHERE token = :t", t=tok) == 1
    assert _pg_scalar(target, "SELECT count(*) FROM workshop WHERE admin_token = :t", t=admin_token) == 1
    # source untouched (read-only)
    assert _sha(source) == before_sha


def test_small_batch_size_gives_identical_result(source, target):
    assert _run(source, target, batch_size=7) == imp.EXIT_OK
    assert _pg_counts(target) == _sqlite_counts(source)


def _api_payloads(monkeypatch, url: str, participant_token: str, admin_token: str) -> dict:
    import src.workshop0.config.settings as settings_module
    from src.workshop0.api import create_app
    from src.workshop0.db.session import reset_db_state

    monkeypatch.setenv("DATABASE_URL", url)
    settings_module._settings = None
    reset_db_state()
    client = TestClient(create_app())
    state = client.get(f"/api/p/{participant_token}/state?v=-1").json()["data"]
    dash = client.get(f"/api/f/{admin_token}/dashboard").json()["data"]
    reset_db_state()
    settings_module._settings = None
    return {"state": state, "dash": dash}


def test_leaderboard_over_imported_db_equals_source(monkeypatch, source, target, tmp_path):
    sconn = sqlite3.connect(f"file:{source}?mode=ro&immutable=1", uri=True)
    admin_token, wid = sconn.execute(
        "SELECT admin_token, id FROM workshop WHERE name = 'Fixture Big Workshop'"
    ).fetchone()
    ptoken = sconn.execute(
        "SELECT token FROM participant WHERE workshop_id = ? ORDER BY id DESC LIMIT 1", (wid,)
    ).fetchone()[0]
    sconn.close()

    assert _run(source, target) == imp.EXIT_OK

    work = tmp_path / "api-copy.db"  # the app opens SQLite read-write: use a throw-away copy
    shutil.copy(source, work)
    from_sqlite = _api_payloads(monkeypatch, f"sqlite:///{work}", ptoken, admin_token)
    from_pg = _api_payloads(monkeypatch, target, ptoken, admin_token)

    board = from_sqlite["state"]["leaderboard"]
    assert len(board) >= 15 and board == from_pg["state"]["leaderboard"]
    assert from_sqlite["state"]["me"] == from_pg["state"]["me"]
    assert from_sqlite["state"]["participants_count"] == from_pg["state"]["participants_count"] >= 300
    assert from_sqlite["state"]["version"] == from_pg["state"]["version"]
    for key in ("workshop", "milestones", "participants", "participants_count", "distribution"):
        if key in from_sqlite["dash"]:
            assert from_sqlite["dash"][key] == from_pg["dash"][key], key
    assert from_sqlite["dash"].get("participants") or from_sqlite["dash"].get("participants_count")


def test_sequences_reset_so_fresh_inserts_get_ids_above_imported_max(monkeypatch, source, target):
    assert _run(source, target) == imp.EXIT_OK
    maxima = {t: _pg_scalar(target, f'SELECT max(id) FROM "{t}"') for t in ID_TABLES}
    assert maxima["participant"] >= 300
    sconn = sqlite3.connect(f"file:{source}?mode=ro&immutable=1", uri=True)
    slug = sconn.execute("SELECT join_slug FROM workshop WHERE name = 'Fixture Big Workshop'").fetchone()[0]
    sconn.close()

    # Through the real app: a brand-new participant gets max(id)+1, not a duplicate-key error.
    import src.workshop0.config.settings as settings_module
    from src.workshop0.api import create_app
    from src.workshop0.db.session import reset_db_state

    monkeypatch.setenv("DATABASE_URL", target)
    settings_module._settings = None
    reset_db_state()
    client = TestClient(create_app())
    joined = client.post(f"/api/join/{slug}", json={"name": "After Import"})
    assert joined.status_code == 200, joined.text
    token = joined.json()["data"]["participant_token"]
    assert _pg_scalar(target, "SELECT id FROM participant WHERE token = :t", t=token) == maxima["participant"] + 1
    reset_db_state()
    settings_module._settings = None

    # And for every other table with rows, the next sequence value is exactly max(id)+1.
    for t in ID_TABLES:
        if t == "participant" or not maxima[t]:
            continue
        nxt = _pg_scalar(target, f"SELECT nextval(pg_get_serial_sequence('\"{t}\"', 'id'))")
        assert nxt == maxima[t] + 1, t


def test_empty_source_tables_get_sequences_that_start_at_one(source, target):
    # ai_usage etc. may be empty in a source: setval(…, 1, false) -> first id is 1, not 2
    conn = sqlite3.connect(source)
    conn.execute("DELETE FROM ai_usage")
    conn.commit()
    conn.close()
    assert _run(source, target) == imp.EXIT_OK
    assert _pg_counts(target)["ai_usage"] == 0
    assert _pg_scalar(target, "SELECT nextval(pg_get_serial_sequence('ai_usage', 'id'))") == 1


def test_topic_reference_table_is_replaced_by_the_source_including_admin_edits(source, target):
    """Both sides carry the 40-topic seed (same revision). The target's seed must not
    count as "already has data", and the source's admin-added / renamed topics — and a
    listing tagged with them — must arrive intact, with the topic sequence past them."""
    assert _pg_scalar(target, "SELECT count(*) FROM topic") == SEEDED_TOPICS
    conn = sqlite3.connect(source)
    assert conn.execute("SELECT count(*) FROM topic").fetchone()[0] == SEEDED_TOPICS
    conn.execute(
        "INSERT INTO topic (id, slug, name, category, position, active, created_at, updated_at)"
        " VALUES (41, 'elixir', 'Elixir', 'Languages', 40, 1, '2026-11-01 10:00:00', '2026-11-01 10:00:00')"
    )
    conn.execute("UPDATE topic SET name = 'Golang', active = 0 WHERE slug = 'go'")
    conn.execute(
        "INSERT INTO opportunity (id, title, type, summary, description_md, location_mode, city,"
        " starts_on, ends_on, deadline, status, published_at, created_at, updated_at)"
        " VALUES (1, 'Elixir bootcamp', 'engagement', 'Teach Elixir', '', 'onsite', 'Pune',"
        " '2026-12-05', '2026-12-06', '2026-11-30 18:29:59', 'open', '2026-11-01 10:00:00',"
        " '2026-11-01 10:00:00', '2026-11-01 10:00:00')"
    )
    conn.execute("INSERT INTO opportunity_topic (opportunity_id, topic_id) VALUES (1, 41)")
    conn.commit()
    conn.close()

    assert _run(source, target) == imp.EXIT_OK
    assert _pg_counts(target) == _sqlite_counts(source)
    assert _pg_scalar(target, "SELECT count(*) FROM topic") == SEEDED_TOPICS + 1
    assert _pg_scalar(target, "SELECT name FROM topic WHERE slug = 'elixir'") == "Elixir"
    assert _pg_scalar(target, "SELECT active FROM topic WHERE slug = 'elixir'") is True
    assert _pg_scalar(target, "SELECT name FROM topic WHERE slug = 'go'") == "Golang"
    assert _pg_scalar(target, "SELECT active FROM topic WHERE slug = 'go'") is False
    assert _pg_scalar(target, "SELECT starts_on FROM opportunity WHERE id = 1").isoformat() == "2026-12-05"
    assert _pg_scalar(target, "SELECT deadline FROM opportunity WHERE id = 1") == datetime(
        2026, 11, 30, 18, 29, 59, tzinfo=timezone.utc
    )
    assert _pg_scalar(target, "SELECT topic_id FROM opportunity_topic WHERE opportunity_id = 1") == 41
    assert _pg_scalar(target, "SELECT nextval(pg_get_serial_sequence('topic', 'id'))") == 42


def test_a_target_holding_only_the_topic_seed_is_not_refused_but_other_data_is(source, target, capsys):
    assert _run(source, target) == imp.EXIT_OK  # seed-only target: imported, not refused
    capsys.readouterr()
    engine = create_engine(target)
    with engine.begin() as c:  # leave only the topic table populated
        c.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in APP_TABLES if t != "topic") + " CASCADE"))
    engine.dispose()
    assert _run(source, target) == imp.EXIT_OK
    assert _pg_counts(target) == _sqlite_counts(source)


# --------------------------------------------------------------------------- refusals


def test_non_empty_target_without_replace_aborts_and_changes_nothing(source, target, capsys):
    assert _run(source, target) == imp.EXIT_OK
    capsys.readouterr()
    before = _pg_counts(target)
    engine = create_engine(target)
    with engine.begin() as c:
        c.execute(text("DELETE FROM milestone_completion"))  # make the target distinguishable
    engine.dispose()
    damaged = _pg_counts(target)
    assert damaged != before

    assert _run(source, target) == imp.EXIT_REFUSED
    out = capsys.readouterr().out
    assert "--replace" in out and "REFUSED" in out
    assert _pg_counts(target) == damaged  # nothing changed


def test_replace_wipes_prints_counts_and_is_idempotent(source, target, capsys):
    assert _run(source, target) == imp.EXIT_OK

    def fingerprint():
        return (
            _pg_counts(target),
            _pg_scalar(target, "SELECT md5(string_agg(token || id::text, ',' ORDER BY id)) FROM participant"),
            _pg_scalar(target, "SELECT md5(string_agg(participant_id::text || ':' || milestone_id::text, ',' ORDER BY id)) FROM milestone_completion"),
        )

    first = fingerprint()
    capsys.readouterr()
    assert _run(source, target, replace=True) == imp.EXIT_OK
    out = capsys.readouterr().out
    assert "--replace: deleting existing rows" in out
    assert f"participant: {first[0]['participant']}" in out  # prints what it will delete
    assert fingerprint() == first
    assert _run(source, target, replace=True) == imp.EXIT_OK
    assert fingerprint() == first


def test_revision_mismatch_aborts_before_writing(source, target, capsys):
    conn = sqlite3.connect(source)
    conn.execute("UPDATE alembic_version SET version_num = '0003'")
    conn.commit()
    conn.close()
    assert _run(source, target) == imp.EXIT_REFUSED
    out = capsys.readouterr().out
    assert "mismatch" in out and "0003" in out and "alembic upgrade head" in out
    _assert_target_untouched(target)


def test_unmigrated_target_and_bad_inputs_are_refused(source, scratch_database, tmp_path, capsys):
    blank = scratch_database()  # no alembic run
    assert _run(source, blank) == imp.EXIT_REFUSED
    assert "run the migrations" in capsys.readouterr().out
    assert imp.run_import(tmp_path / "missing.db", blank) == imp.EXIT_REFUSED
    junk = tmp_path / "junk.db"
    junk.write_text("not a database")
    assert imp.run_import(junk, blank) == imp.EXIT_REFUSED
    assert imp.run_import(source, f"sqlite:///{tmp_path}/x.db") == imp.EXIT_REFUSED


# --------------------------------------------------------------------------- atomicity


def test_forced_mid_copy_failure_leaves_target_empty(source, target, capsys):
    """An answer pointing at a help request that does not exist fails in the LAST table,
    after workshop, participant, completions, ... were already copied: all must roll back."""
    conn = sqlite3.connect(source)
    conn.execute("UPDATE help_answer SET help_request_id = 99999 WHERE id = 1")
    conn.commit()
    conn.close()

    assert _run(source, target) == imp.EXIT_FAILED
    out = capsys.readouterr().out
    assert "copied participant" in out and "copied milestone_completion" in out  # it got far
    assert "FAILED" in out and "Rolled back" in out
    _assert_target_untouched(target)
    assert _pg_scalar(target, "SELECT count(*) FROM alembic_version") == 1  # untouched


def test_failure_after_a_table_via_hook_rolls_back_everything(source, target):
    def boom(table: str) -> None:
        if table == "milestone_completion":
            raise RuntimeError("simulated crash")

    assert imp.run_import(source, target, _after_table=boom) == imp.EXIT_FAILED
    _assert_target_untouched(target)


def test_failed_replace_keeps_the_previous_data(source, target):
    assert _run(source, target) == imp.EXIT_OK
    before = _pg_counts(target)
    conn = sqlite3.connect(source)
    conn.execute("UPDATE help_answer SET help_request_id = 99999 WHERE id = 1")
    conn.commit()
    conn.close()
    assert _run(source, target, replace=True) == imp.EXIT_FAILED
    assert _pg_counts(target) == before  # the TRUNCATE was rolled back too


def test_verification_mismatch_exits_nonzero_and_rolls_back(monkeypatch, source, target, capsys):
    real = imp.count_source
    monkeypatch.setattr(imp, "count_source", lambda s, t: real(s, t) + (1 if t == "broadcast" else 0))
    assert _run(source, target) == imp.EXIT_FAILED
    out = capsys.readouterr().out
    assert any(line.startswith("broadcast") and line.rstrip().endswith("MISMATCH") for line in out.splitlines())
    assert "FAILED" in out
    _assert_target_untouched(target)


# --------------------------------------------------------------------------- real-world quirks


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2026-03-04 05:06:07.123456", datetime(2026, 3, 4, 5, 6, 7, 123456, tzinfo=timezone.utc)),
        ("2026-03-04 05:06:07", datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc)),
        ("2026-03-04T05:06:07.5", datetime(2026, 3, 4, 5, 6, 7, 500000, tzinfo=timezone.utc)),
        ("2026-03-04T05:06:07Z", datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc)),
        ("2026-03-04 05:06:07.123456+00:00", datetime(2026, 3, 4, 5, 6, 7, 123456, tzinfo=timezone.utc)),
        ("2026-03-04 10:36:07+05:30", datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc)),
        ("2026-03-04 05:06:07.1234567", datetime(2026, 3, 4, 5, 6, 7, 123456, tzinfo=timezone.utc)),
        ("  2026-03-04 05:06:07  ", datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc)),
        (1772600767, datetime.fromtimestamp(1772600767, tz=timezone.utc)),
        (b"2026-03-04 05:06:07", datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc)),
    ],
)
def test_parse_datetime_variants(raw, expected):
    got = imp.parse_datetime(raw)
    assert got == expected and got.utcoffset() == timedelta(0)


@pytest.mark.parametrize("raw, expected", [(1, True), (0, False), ("1", True), ("0", False),
                                           ("true", True), ("False", False), ("t", True), (True, True), (1.0, True)])
def test_parse_bool_variants(raw, expected):
    assert imp.parse_bool(raw) is expected


def test_garbage_datetime_or_bool_fails_with_location_not_value(source, target, capsys):
    conn = sqlite3.connect(source)
    conn.execute("UPDATE workshop SET ended_at = 'SECRET-garbage' WHERE id = 1")
    conn.commit()
    conn.close()
    assert _run(source, target) == imp.EXIT_FAILED
    out = capsys.readouterr().out
    assert "workshop.ended_at" in out and "SECRET-garbage" not in out
    _assert_target_untouched(target)


def test_old_app_style_values_import_correctly(source, target):
    """Text/NULL/format variants a long-lived production file may carry."""
    conn = sqlite3.connect(source)
    conn.execute("UPDATE workshop SET created_at = '2026-01-02 03:04:05', starts_at = '2026-01-02T08:34:05+05:30',"
                 " ended_at = NULL, paused = 'true', ai_enabled = 'f', grace_until = '2026-01-03 00:00:00.5' WHERE id = 2")
    conn.execute("UPDATE participant SET last_seen_at = '2026-01-02T03:04:05Z' WHERE id = 1")
    conn.execute("UPDATE help_request SET ai_state = NULL, resolved_by = NULL, escalated = '0' WHERE id = 1")
    conn.execute("UPDATE help_answer SET ai_confidence = '0.875', draft = 1 WHERE id = 1")
    conn.execute("UPDATE ai_usage SET cost_usd = 0.5 WHERE id = 1")
    conn.execute("UPDATE milestone SET input_config_json = NULL, minutes = NULL WHERE id = 1")
    conn.commit()
    conn.close()

    assert _run(source, target) == imp.EXIT_OK
    utc = lambda *a, **k: datetime(*a, tzinfo=timezone.utc, **k)  # noqa: E731
    assert _pg_scalar(target, "SELECT created_at FROM workshop WHERE id = 2") == utc(2026, 1, 2, 3, 4, 5)
    assert _pg_scalar(target, "SELECT starts_at FROM workshop WHERE id = 2") == utc(2026, 1, 2, 3, 4, 5)
    assert _pg_scalar(target, "SELECT grace_until FROM workshop WHERE id = 2") == utc(2026, 1, 3, 0, 0, 0, microsecond=500000)
    assert _pg_scalar(target, "SELECT ended_at FROM workshop WHERE id = 2") is None
    assert _pg_scalar(target, "SELECT paused FROM workshop WHERE id = 2") is True
    assert _pg_scalar(target, "SELECT ai_enabled FROM workshop WHERE id = 2") is False
    assert _pg_scalar(target, "SELECT last_seen_at FROM participant WHERE id = 1") == utc(2026, 1, 2, 3, 4, 5)
    assert _pg_scalar(target, "SELECT escalated FROM help_request WHERE id = 1") is False
    assert float(_pg_scalar(target, "SELECT ai_confidence FROM help_answer WHERE id = 1")) == 0.875
    assert _pg_scalar(target, "SELECT draft FROM help_answer WHERE id = 1") is True
    assert float(_pg_scalar(target, "SELECT cost_usd FROM ai_usage WHERE id = 1")) == 0.5
    assert _pg_scalar(target, "SELECT minutes FROM milestone WHERE id = 1") is None


def test_naive_stored_time_is_read_as_utc_regardless_of_session_timezone(source, target):
    conn = sqlite3.connect(source)
    stored = conn.execute("SELECT joined_at FROM participant WHERE id = 3").fetchone()[0]
    conn.close()
    assert _run(source, target) == imp.EXIT_OK
    engine = create_engine(target)
    with engine.connect() as c:
        c.execute(text("SET TIME ZONE 'Asia/Kolkata'"))
        got = c.execute(text("SELECT joined_at FROM participant WHERE id = 3")).scalar()
    engine.dispose()
    assert got == datetime.fromisoformat(stored).replace(tzinfo=timezone.utc)


def test_self_referencing_clone_pointer_is_preserved_even_when_pointing_forward(source, target):
    conn = sqlite3.connect(source)
    conn.execute("UPDATE workshop SET cloned_from_id = 3 WHERE id = 1")  # parent has a LARGER id
    conn.execute("UPDATE workshop SET cloned_from_id = 1 WHERE id = 2")
    conn.commit()
    conn.close()
    assert _run(source, target) == imp.EXIT_OK
    assert _pg_scalar(target, "SELECT cloned_from_id FROM workshop WHERE id = 1") == 3
    assert _pg_scalar(target, "SELECT cloned_from_id FROM workshop WHERE id = 2") == 1


# --------------------------------------------------------------------------- CLI


def _cli(*args, env=None):
    import os

    e = {k: v for k, v in os.environ.items() if k not in ("TARGET_DATABASE_URL", "DATABASE_URL")}
    e.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "sqlite_to_postgres.py"), *args],
        cwd="/", capture_output=True, text=True, env=e, timeout=300,
    )


def test_cli_with_env_target_prints_verification_table(source, target):
    result = _cli("--sqlite", str(source), env={"TARGET_DATABASE_URL": target})
    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
    header = [line for line in result.stdout.splitlines() if line.startswith("table")]
    assert header and header[0].split() == ["table", "source", "target", "orphans", "status"]
    assert "[import] committed" in result.stdout
    assert _pg_counts(target) == _sqlite_counts(source)
    assert "@" not in result.stdout  # no credentials echoed


def test_cli_target_url_flag_database_url_fallback_and_replace(source, target):
    assert _cli("--sqlite", str(source), "--target-url", target).returncode == 0
    again = _cli("--sqlite", str(source), env={"DATABASE_URL": target})
    assert again.returncode == 2 and "--replace" in again.stdout
    assert _cli("--sqlite", str(source), "--replace", "--batch-size", "100", env={"DATABASE_URL": target}).returncode == 0


def test_cli_without_target_exits_2():
    result = _cli("--sqlite", "/nonexistent.db")
    assert result.returncode == 2 and "no target" in result.stdout


def test_cli_bad_batch_size_is_a_usage_error(source, target):
    result = _cli("--sqlite", str(source), "--target-url", target, "--batch-size", "0")
    assert result.returncode == 2
    _assert_target_untouched(target)


def test_fixture_generator_refuses_to_overwrite(fixture_db):
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "make_import_fixture.py"), "--out", str(fixture_db)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode != 0 and "refusing to overwrite" in (result.stderr + result.stdout)
