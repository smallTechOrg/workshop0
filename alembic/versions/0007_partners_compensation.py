"""Phase 11b: partner table, opportunity.partner_id + structured compensation columns,
ai_usage.purpose widened to String(32), free-text partner data migration
(spec/data-model.md §Phase 11b). Does not import app code.

Revision ID: 0007
Revises: 0006
"""

from collections import Counter
from datetime import datetime, timezone
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels = None
depends_on = None


def _sort_key(row) -> tuple:
    # (updated_at, id); updated_at may be naive on SQLite — compare as naive UTC.
    ts = row["updated_at"]
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if ts is not None and ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    return (ts or datetime.min, row["id"])


def _migrate_partners(bind) -> None:
    rows = [
        dict(r._mapping)
        for r in bind.execute(sa.text(
            "SELECT id, partner_internal_name, partner_display_name, updated_at FROM opportunity"
        ))
    ]
    groups: dict[str, list[dict]] = {}
    for row in rows:
        name = row["partner_internal_name"]
        if name is None or not name.strip():
            continue
        collapsed = " ".join(name.split())
        row["collapsed"] = collapsed
        groups.setdefault(collapsed.casefold(), []).append(row)

    partner = sa.table(
        "partner",
        sa.column("id", sa.Integer),
        sa.column("internal_name", sa.String),
        sa.column("name_key", sa.String),
        sa.column("display_name", sa.String),
        sa.column("notes", sa.Text),
        sa.column("active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(timezone.utc)
    for key in sorted(groups):
        members = groups[key]
        latest = max(members, key=_sort_key)
        displays = [
            (" ".join(m["partner_display_name"].split()), m)
            for m in members
            if m["partner_display_name"] and m["partner_display_name"].strip()
        ]
        display = None
        if displays:
            counts = Counter(d for d, _ in displays)
            best = max(counts.values())
            tied = [(d, m) for d, m in displays if counts[d] == best]
            display = max(tied, key=lambda dm: _sort_key(dm[1]))[0]
        bind.execute(sa.insert(partner).values(
            internal_name=latest["collapsed"], name_key=key, display_name=display,
            notes=None, active=True, created_at=now, updated_at=now,
        ))
        pid = bind.execute(
            sa.text("SELECT id FROM partner WHERE name_key = :k"), {"k": key}
        ).scalar_one()
        for m in members:
            bind.execute(
                sa.text("UPDATE opportunity SET partner_id = :p WHERE id = :i"),
                {"p": pid, "i": m["id"]},
            )


def upgrade() -> None:
    op.create_table(
        "partner",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("internal_name", sa.String(160), nullable=False),
        sa.Column("name_key", sa.String(200), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partner")),
        sa.UniqueConstraint("name_key", name=op.f("uq_partner_name_key")),
    )

    with op.batch_alter_table("opportunity") as batch:
        batch.add_column(sa.Column("partner_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("compensation_min", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("compensation_max", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("compensation_currency", sa.String(3), nullable=True))
        batch.add_column(sa.Column("compensation_unit", sa.String(8), nullable=True))
        batch.create_foreign_key(
            op.f("fk_opportunity_partner_id_partner"), "partner", ["partner_id"], ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index("ix_opportunity_partner_id", ["partner_id"])

    with op.batch_alter_table("ai_usage") as batch:
        batch.alter_column("purpose", existing_type=sa.String(16), type_=sa.String(32), existing_nullable=False)

    _migrate_partners(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE opportunity SET partner_internal_name = "
        "(SELECT internal_name FROM partner WHERE partner.id = opportunity.partner_id) "
        "WHERE partner_id IS NOT NULL"
    ))
    rows = bind.execute(sa.text(
        "SELECT id, compensation_min, compensation_max, compensation_currency, compensation_unit "
        "FROM opportunity WHERE compensation_text IS NULL "
        "AND (compensation_min IS NOT NULL OR compensation_max IS NOT NULL)"
    )).all()
    for r in rows:
        if r.compensation_min is not None and r.compensation_max is not None:
            amount = f"{r.compensation_min}-{r.compensation_max}"
        else:
            amount = str(r.compensation_min if r.compensation_min is not None else r.compensation_max)
        text = " ".join(p for p in (r.compensation_currency, amount) if p)
        if r.compensation_unit:
            text += f" / {r.compensation_unit}"
        bind.execute(
            sa.text("UPDATE opportunity SET compensation_text = :t WHERE id = :i"),
            {"t": text[:120], "i": r.id},
        )

    with op.batch_alter_table("opportunity") as batch:
        batch.drop_index("ix_opportunity_partner_id")
        batch.drop_constraint(op.f("fk_opportunity_partner_id_partner"), type_="foreignkey")
        batch.drop_column("compensation_unit")
        batch.drop_column("compensation_currency")
        batch.drop_column("compensation_max")
        batch.drop_column("compensation_min")
        batch.drop_column("partner_id")
    op.drop_table("partner")

    op.execute("DELETE FROM ai_usage WHERE length(purpose) > 16")
    with op.batch_alter_table("ai_usage") as batch:
        batch.alter_column("purpose", existing_type=sa.String(32), type_=sa.String(16), existing_nullable=False)
