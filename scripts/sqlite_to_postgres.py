"""One-shot, verified, all-or-nothing import of a Workshop0 SQLite database into PostgreSQL.

    uv run python scripts/sqlite_to_postgres.py --sqlite PATH
        [--target-url URL]          # else env TARGET_DATABASE_URL, else env DATABASE_URL
        [--replace]                 # wipe the target's app tables first (prints counts)
        [--batch-size 500]

What it does (see spec/roadmap.md, Phase 8 / S1):
  * opens the source READ-ONLY (`file:PATH?mode=ro`); never writes to it
  * aborts unless source and target `alembic_version` are equal
  * aborts if any app table in the target has rows, unless --replace
    (`TRUNCATE ... RESTART IDENTITY CASCADE`, inside the same transaction).
    Reference tables (`topic`: migration-seeded, then admin-edited) are excluded from
    that check and are ALWAYS truncated and re-copied from the source — same alembic
    revision means the same seed, plus the source admin's edits
  * copies every app table in FK order (Base.metadata.sorted_tables), in batches,
    in ONE transaction: naive SQLite datetimes are read as UTC, 0/1 become booleans
  * resets every `id` sequence to max(id)
  * verifies per-table COUNT(*) (source vs target) and FK orphans, prints a table,
    and exits non-zero (rolling everything back) on any mismatch
  * never prints row data (PII): only table names, counts and column names

Exit codes: 0 imported and verified; 1 failed (rolled back, target untouched);
2 refused before touching the target (usage, revision mismatch, non-empty target).
Re-running with --replace is idempotent: the target ends up identical every time.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # `python scripts/x.py` puts scripts/ on the path, not the repo
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import (  # noqa: E402
    Boolean,
    Date,
    DateTime,
    Integer,
    Numeric,
    Table,
    create_engine,
    text,
)
from sqlalchemy.engine import Connection, make_url  # noqa: E402

from src.workshop0.db.models import Base  # noqa: E402

EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2

# Migration-seeded reference data: a freshly migrated target already holds these rows,
# so they never count as "target already has data" and are always replaced by the source's.
REFERENCE_TABLES = ("topic",)


class ImportRefused(Exception):
    """A pre-flight check failed before anything was written."""


class ImportFailed(Exception):
    """The copy or its verification failed; the transaction is rolled back."""


def log(message: str = "") -> None:
    print(message, flush=True)


# --------------------------------------------------------------------------- values

_TRUE = {"1", "true", "t", "yes", "y", "on"}
_FALSE = {"0", "false", "f", "no", "n", "off", ""}
_FRACTION = re.compile(r"(\.\d+)")


def parse_datetime(value: Any) -> datetime:
    """SQLite datetime -> tz-aware UTC. Naive = UTC; offsets are converted; accepts
    'YYYY-MM-DD HH:MM:SS[.ffffff]', ISO 'T', trailing 'Z' or +HH:MM, and epoch numbers."""
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, bool):
        raise ValueError("boolean is not a datetime")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    s = str(value).strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", s):
        return datetime.fromtimestamp(float(s), tz=timezone.utc)
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    s = re.sub(r"\s*(UTC|GMT)$", "+00:00", s)
    # normalise fractional seconds to <= 6 digits (older writers used 7+ or 1-2)
    s = _FRACTION.sub(lambda m: (m.group(1) + "000000")[:7], s, count=1)
    parsed = datetime.fromisoformat(s)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_date(value: Any) -> date:
    """SQLite DATE ('YYYY-MM-DD', possibly with a time part) -> date."""
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    s = str(value).strip()
    if len(s) > 10 and s[10] in " T":
        return parse_datetime(s).date()
    return date.fromisoformat(s)


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    s = str(value).strip().lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    raise ValueError("not a boolean")


def convert(column, value: Any) -> Any:
    """Convert one SQLite value for a target column; NULL stays NULL (NOT NULL is the DB's call)."""
    if value is None:
        return None
    ctype = column.type
    try:
        if isinstance(ctype, Boolean):
            return parse_bool(value)
        if isinstance(ctype, DateTime):
            return parse_datetime(value)
        if isinstance(ctype, Date):
            return parse_date(value)
        if isinstance(ctype, Integer):
            return int(value)
        if isinstance(ctype, Numeric):
            return Decimal(str(value))
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value if isinstance(value, str) else str(value)
    except (ValueError, TypeError, InvalidOperation, OverflowError, OSError) as exc:
        # Never include the value itself (PII) — only where it was.
        raise ImportFailed(
            f"cannot convert a value in {column.table.name}.{column.name} to {ctype!s} ({type(exc).__name__})"
        ) from None


# --------------------------------------------------------------------------- source

def open_source(path: Path) -> sqlite3.Connection:
    """Open read-only. If a WAL database sits on a read-only mount (no -shm possible),
    fall back to immutable=1, which is safe for a quiescent copy (never for a live file)."""
    if not path.is_file():
        raise ImportRefused(f"source SQLite file not found: {path}")
    base = f"file:{path.resolve().as_posix()}"
    last: Exception | None = None
    for query in ("mode=ro", "mode=ro&immutable=1"):
        conn = sqlite3.connect(f"{base}?{query}", uri=True, timeout=10, isolation_level=None)
        try:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
            if query != "mode=ro":
                log("[import] source opened immutable (read-only medium); it must not be changing")
            conn.text_factory = lambda b: b.decode("utf-8", errors="strict")
            conn.execute("BEGIN")  # one consistent read snapshot for counts and rows
            return conn
        except sqlite3.DatabaseError as exc:
            last = exc
            conn.close()
    raise ImportRefused(f"cannot open source as a SQLite database ({type(last).__name__})")


def source_revision(src: sqlite3.Connection) -> str | None:
    try:
        row = src.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.DatabaseError:
        return None
    return str(row[0]) if row else None


def source_tables(src: sqlite3.Connection) -> set[str]:
    return {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def count_source(src: sqlite3.Connection, table: str) -> int:
    return int(src.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])


# --------------------------------------------------------------------------- target

def normalise_url(url: str) -> str:
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix):]
    if not url.startswith("postgresql"):
        raise ImportRefused("target must be a PostgreSQL URL (got a different driver)")
    return url


def target_revision(conn: Connection) -> str | None:
    exists = conn.execute(text("SELECT to_regclass('alembic_version') IS NOT NULL")).scalar()
    if not exists:
        return None
    row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
    return str(row[0]) if row else None


def count_target(conn: Connection, table: str) -> int:
    return int(conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one())


def self_fk_columns(table: Table) -> list[str]:
    return [fk.parent.name for fk in table.foreign_keys if fk.column.table is table]


def orphan_count(conn: Connection, table: Table) -> int:
    total = 0
    for fk in table.foreign_keys:
        child, parent = table.name, fk.column.table.name
        total += int(
            conn.execute(
                text(
                    f'SELECT count(*) FROM "{child}" c LEFT JOIN "{parent}" p '
                    f'ON c."{fk.parent.name}" = p."{fk.column.name}" '
                    f'WHERE c."{fk.parent.name}" IS NOT NULL AND p."{fk.column.name}" IS NULL'
                )
            ).scalar_one()
        )
    return total


def reset_sequence(conn: Connection, table: Table) -> None:
    if "id" not in table.c:
        return
    seq = conn.execute(text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": f'"{table.name}"'}).scalar()
    if seq is None:
        raise ImportFailed(f"{table.name}.id has no serial/identity sequence in the target")
    conn.execute(
        text(
            f'SELECT setval(pg_get_serial_sequence(\'"{table.name}"\', \'id\'), '
            f'COALESCE(max(id), 1), max(id) IS NOT NULL) FROM "{table.name}"'
        )
    )


# --------------------------------------------------------------------------- copy

def copy_table(
    src: sqlite3.Connection, conn: Connection, table: Table, batch_size: int, source_cols: set[str]
) -> int:
    missing = [c.name for c in table.columns if c.name not in source_cols]
    if missing:
        raise ImportRefused(f"source table {table.name} lacks column(s): {', '.join(missing)}")
    cols = list(table.columns)
    names = ", ".join(f'"{c.name}"' for c in cols)
    order = '"id"' if "id" in table.c else "rowid"
    cursor = src.execute(f'SELECT {names} FROM "{table.name}" ORDER BY {order}')
    deferred = self_fk_columns(table)  # e.g. workshop.cloned_from_id: fix up after all rows exist
    insert = table.insert()
    copied = 0
    fixups: list[dict] = []
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        batch = []
        for row in rows:
            record = {c.name: convert(c, v) for c, v in zip(cols, row)}
            for name in deferred:
                if record[name] is not None:
                    fixups.append({"_id": record["id"], "_ref": record[name]})
                    record[name] = None
            batch.append(record)
        conn.execute(insert, batch)
        copied += len(batch)
    if fixups:
        col = deferred[0]
        conn.execute(
            text(f'UPDATE "{table.name}" SET "{col}" = :_ref WHERE id = :_id'), fixups
        )
    return copied


# --------------------------------------------------------------------------- driver

def run_import(
    sqlite_path: Path,
    target_url: str,
    *,
    replace: bool = False,
    batch_size: int = 500,
    _after_table: Callable[[str], None] | None = None,
) -> int:
    """Run the whole import; returns an exit code. `_after_table` is a test seam only."""
    tables = list(Base.metadata.sorted_tables)  # FK order; alembic_version is not in the metadata
    src: sqlite3.Connection | None = None
    engine = None
    try:
        url = make_url(normalise_url(target_url))
        engine = create_engine(url, pool_pre_ping=True)
        src = open_source(sqlite_path)
        log(f"[import] source: {sqlite_path.name} (read-only)")
        log(f"[import] target: {url.host or 'localhost'}:{url.port or 5432}/{url.database}")

        src_rev = source_revision(src)
        missing_src = [t.name for t in tables if t.name not in source_tables(src)]
        if src_rev is None or missing_src:
            raise ImportRefused(
                "source has no alembic_version / is missing app tables"
                + (f" ({', '.join(missing_src)})" if missing_src else "")
                + ". Is it a Workshop0 database?"
            )

        with engine.connect() as probe:
            tgt_rev = target_revision(probe)
        if tgt_rev is None:
            raise ImportRefused(
                "target has no alembic_version: run the migrations first "
                "(`uv run alembic upgrade head` with DATABASE_URL pointing at the target)"
            )
        log(f"[import] alembic revision: source={src_rev} target={tgt_rev}")
        if src_rev != tgt_rev:
            raise ImportRefused(
                f"alembic revision mismatch (source {src_rev}, target {tgt_rev}). Upgrade a "
                "scratch COPY of the source to the target's revision, never the original: "
                "`cp SRC /tmp/copy.db && DATABASE_URL=sqlite:////tmp/copy.db uv run alembic upgrade head`"
                " (or point the target at the matching app image)."
            )

        src_cols = {
            t.name: {r[1] for r in src.execute(f'PRAGMA table_info("{t.name}")')} for t in tables
        }
        source_counts = {t.name: count_source(src, t.name) for t in tables}

        with engine.connect() as conn:
            trans = conn.begin()
            try:
                existing = {t.name: count_target(conn, t.name) for t in tables}
                if any(n for name, n in existing.items() if name not in REFERENCE_TABLES):
                    if not replace:
                        raise ImportRefused(
                            "target already has data ("
                            + ", ".join(f"{k}={v}" for k, v in existing.items() if v)
                            + "); nothing changed. Re-run with --replace to wipe and re-import."
                        )
                    log("[import] --replace: deleting existing rows:")
                    for name, n in existing.items():
                        log(f"[import]   {name}: {n}")
                    names = ", ".join(f'"{t.name}"' for t in tables)
                    conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
                else:
                    # Only reference rows (the seed) are present: replace them with the
                    # source's. Every dependent table is empty here (checked above).
                    names = ", ".join(f'"{t}"' for t in REFERENCE_TABLES)
                    conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))

                for table in tables:
                    n = copy_table(src, conn, table, batch_size, src_cols[table.name])
                    log(f"[import] copied {table.name}: {n}")
                    if _after_table:
                        _after_table(table.name)

                for table in tables:
                    reset_sequence(conn, table)

                ok = verify(conn, tables, source_counts)
                if not ok:
                    raise ImportFailed("verification failed")
                trans.commit()
            except BaseException:
                trans.rollback()
                raise
        log("[import] committed. Import complete and verified.")
        return EXIT_OK
    except ImportRefused as exc:
        log(f"[import] REFUSED: {exc}")
        return EXIT_REFUSED
    except ImportFailed as exc:
        log(f"[import] FAILED: {exc}. Rolled back; the target is unchanged.")
        return EXIT_FAILED
    except Exception as exc:  # DB errors can echo row values in their text: print the type only
        log(f"[import] FAILED: {type(exc).__name__} during the copy. Rolled back; the target is unchanged.")
        log("[import] (re-run with --debug for the full error; it may contain row data)")
        if os.environ.get("WORKSHOP0_IMPORT_DEBUG"):
            raise
        return EXIT_FAILED
    finally:
        if src is not None:
            src.close()
        if engine is not None:
            engine.dispose()


def verify(conn: Connection, tables: list[Table], source_counts: dict[str, int]) -> bool:
    log("")
    log(f"{'table':<28}{'source':>9}{'target':>9}{'orphans':>9}  status")
    all_ok = True
    total_src = total_tgt = 0
    for t in tables:
        tgt = count_target(conn, t.name)
        src_n = source_counts[t.name]
        orphans = orphan_count(conn, t)
        status = "OK" if tgt == src_n and orphans == 0 else "MISMATCH"
        all_ok &= status == "OK"
        total_src += src_n
        total_tgt += tgt
        log(f"{t.name:<28}{src_n:>9}{tgt:>9}{orphans:>9}  {status}")
    log(f"{'TOTAL':<28}{total_src:>9}{total_tgt:>9}{'':>9}  {'OK' if all_ok else 'MISMATCH'}")
    log("")
    return all_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import a Workshop0 SQLite database into PostgreSQL.")
    parser.add_argument("--sqlite", required=True, type=Path, help="source SQLite file (opened read-only)")
    parser.add_argument("--target-url", help="PostgreSQL URL (else env TARGET_DATABASE_URL, else DATABASE_URL)")
    parser.add_argument("--replace", action="store_true", help="wipe the target's app tables first")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--debug", action="store_true", help="re-raise unexpected errors (may print row data)")
    args = parser.parse_args(argv)
    if args.debug:
        os.environ["WORKSHOP0_IMPORT_DEBUG"] = "1"
    if args.batch_size < 1:
        parser.error("--batch-size must be >= 1")
    url = args.target_url or os.environ.get("TARGET_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        log("[import] REFUSED: no target: pass --target-url or set TARGET_DATABASE_URL (or DATABASE_URL)")
        return EXIT_REFUSED
    return run_import(args.sqlite, url, replace=args.replace, batch_size=args.batch_size)


if __name__ == "__main__":
    raise SystemExit(main())
