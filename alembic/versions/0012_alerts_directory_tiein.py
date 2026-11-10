"""Phase 13: saved searches, email prefs, workshop facilitators, trainer public slug,
opportunity.workshop_id (spec/data-model.md Phase 13). Purely additive.

Revision ID: 0012
Revises: 0011
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_search",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("criteria_json", sa.Text(), nullable=False),
        sa.Column("alerts_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_saved_search_user_id", "saved_search", ["user_id"])

    op.create_table(
        "email_pref",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("alerts", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("digest", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "workshop_facilitator",
        sa.Column("workshop_id", sa.Integer(), sa.ForeignKey("workshop.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "profile_id", sa.Integer(), sa.ForeignKey("trainer_profile.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("role", sa.String(length=8), nullable=False),
        sa.Column("linked_by", sa.String(length=254), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workshop_facilitator_profile_id", "workshop_facilitator", ["profile_id"])

    with op.batch_alter_table("trainer_profile") as batch:
        batch.add_column(sa.Column("public_slug", sa.String(length=80), nullable=True))
        batch.create_unique_constraint("uq_trainer_profile_public_slug", ["public_slug"])

    with op.batch_alter_table("opportunity") as batch:
        batch.add_column(sa.Column("workshop_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_opportunity_workshop_id_workshop", "workshop", ["workshop_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index("ix_opportunity_workshop_id", ["workshop_id"])


def downgrade() -> None:
    with op.batch_alter_table("opportunity") as batch:
        batch.drop_index("ix_opportunity_workshop_id")
        batch.drop_constraint("fk_opportunity_workshop_id_workshop", type_="foreignkey")
        batch.drop_column("workshop_id")

    with op.batch_alter_table("trainer_profile") as batch:
        batch.drop_constraint("uq_trainer_profile_public_slug", type_="unique")
        batch.drop_column("public_slug")

    op.drop_index("ix_workshop_facilitator_profile_id", table_name="workshop_facilitator")
    op.drop_table("workshop_facilitator")
    op.drop_table("email_pref")
    op.drop_index("ix_saved_search_user_id", table_name="saved_search")
    op.drop_table("saved_search")
