"""Phase 11c: opportunity.locations_json (multi-location listings) with a data
migration from the single ``city`` column (spec/data-model.md §Phase 11c).
Does not import app code.

Downgrade restores ``city`` from the first location; the second and later
locations are LOST on downgrade (accepted, documented).

Revision ID: 0008
Revises: 0007
"""

import json
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("opportunity") as batch:
        batch.add_column(sa.Column("locations_json", sa.Text(), nullable=False, server_default="[]"))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, city, location_mode FROM opportunity")).all()
    for r in rows:
        if r.location_mode == "remote" or r.city is None or not r.city.strip():
            continue
        value = json.dumps([{"city": " ".join(r.city.split()), "country": None}], ensure_ascii=False)
        bind.execute(
            sa.text("UPDATE opportunity SET locations_json = :v WHERE id = :i"), {"v": value, "i": r.id}
        )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, locations_json FROM opportunity")).all()
    for r in rows:
        try:
            locations = json.loads(r.locations_json or "[]")
        except (TypeError, ValueError):
            continue
        if not isinstance(locations, list) or not locations:
            continue
        first = locations[0]
        city = first.get("city") if isinstance(first, dict) else None
        if not isinstance(city, str) or not city:
            continue
        bind.execute(
            sa.text("UPDATE opportunity SET city = :c WHERE id = :i"), {"c": city[:80], "i": r.id}
        )

    with op.batch_alter_table("opportunity") as batch:
        batch.drop_column("locations_json")
