"""Phase 11e: opportunity.slug (spec/data-model.md §Phase 11e).

Adds `slug` String(80), backfills every existing row with a frozen copy of the slug
rule (no app imports), then makes it NOT NULL + unique (`uq_opportunity_slug`).
Every existing row is treated as frozen (published or not).

Downgrade drops the constraint and the column — slugs are lost; a re-upgrade assigns
NEW random suffixes, so previously shared slug URLs would change.

Revision ID: 0010
Revises: 0009
"""

import json
import re
import secrets
import unicodedata
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels = None
depends_on = None

# ---- frozen copy of services/slugs.py (do not import app code from a migration)
_BASE_MAX = 60
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slug_base(title: str, first_city: str | None) -> str:
    raw = f"{title} {first_city}" if first_city else title
    ascii_only = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    base = _NON_ALNUM.sub("-", ascii_only.lower()).strip("-")
    if len(base) > _BASE_MAX:
        cut = base[:_BASE_MAX]
        if base[_BASE_MAX] != "-" and "-" in cut:
            cut = cut[: cut.rindex("-")]
        base = cut.strip("-")
    return base or "opportunity"


def _first_city(locations_json: str | None, city: str | None) -> str | None:
    try:
        parsed = json.loads(locations_json) if locations_json else None
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict) and isinstance(item.get("city"), str) and item["city"].strip():
                return item["city"]
    if city is not None and city.strip():
        return city
    return None


def upgrade() -> None:
    with op.batch_alter_table("opportunity") as batch:
        batch.add_column(sa.Column("slug", sa.String(length=80), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, title, locations_json, city FROM opportunity ORDER BY id")
    ).all()
    used: set[str] = set()
    for row_id, title, locations_json, city in rows:
        base = _slug_base(title or "", _first_city(locations_json, city))
        collisions = 0
        while True:
            slug = f"{base}-{secrets.token_hex(2 if collisions < 5 else 3)}"
            if slug not in used:
                break
            collisions += 1
        used.add(slug)
        connection.execute(
            sa.text("UPDATE opportunity SET slug = :slug WHERE id = :id"), {"slug": slug, "id": row_id}
        )

    with op.batch_alter_table("opportunity") as batch:
        batch.alter_column("slug", existing_type=sa.String(length=80), nullable=False)
        batch.create_unique_constraint("uq_opportunity_slug", ["slug"])


def downgrade() -> None:
    with op.batch_alter_table("opportunity") as batch:
        batch.drop_constraint("uq_opportunity_slug", type_="unique")
        batch.drop_column("slug")
