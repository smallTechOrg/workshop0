"""Phase 12: applications, opportunity invites, match suggestions, email outbox,
plus admin-only matching fields on opportunity (spec/data-model.md Phase 12).

Revision ID: 0011
Revises: 0010
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("opportunity") as batch:
        batch.add_column(sa.Column("budget_min", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("budget_max", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("budget_currency", sa.String(length=3), nullable=True))
        batch.add_column(sa.Column("budget_unit", sa.String(length=8), nullable=True))
        batch.add_column(sa.Column("min_level", sa.String(length=16), nullable=True))

    op.create_table(
        "application",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("opportunity.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("trainer_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("opportunity_id", "profile_id", name="uq_application_opportunity_profile"),
    )
    op.create_index("ix_application_opportunity_status", "application", ["opportunity_id", "status"])
    op.create_index("ix_application_profile_id", "application", ["profile_id"])

    op.create_table(
        "opportunity_invite",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("opportunity.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("trainer_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.String(length=254), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("opportunity_id", "profile_id", name="uq_opportunity_invite_opportunity_profile"),
    )

    op.create_table(
        "match_suggestion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("opportunity.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("trainer_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=22), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("rule_score", sa.Numeric(6, 3), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=True),
        sa.Column("ranked_by", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_match_suggestion_run_rank", "match_suggestion", ["opportunity_id", "run_id", "rank"])

    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("to_email", sa.String(length=254), nullable=False),
        sa.Column("template", sa.String(length=48), nullable=False),
        sa.Column("context_json", sa.Text(), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("dedupe_key", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("dedupe_key", name="uq_email_outbox_dedupe_key"),
    )
    op.create_index("ix_email_outbox_status_created", "email_outbox", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_email_outbox_status_created", table_name="email_outbox")
    op.drop_table("email_outbox")
    op.drop_index("ix_match_suggestion_run_rank", table_name="match_suggestion")
    op.drop_table("match_suggestion")
    op.drop_table("opportunity_invite")
    op.drop_index("ix_application_profile_id", table_name="application")
    op.drop_index("ix_application_opportunity_status", table_name="application")
    op.drop_table("application")
    with op.batch_alter_table("opportunity") as batch:
        batch.drop_column("min_level")
        batch.drop_column("budget_unit")
        batch.drop_column("budget_currency")
        batch.drop_column("budget_max")
        batch.drop_column("budget_min")
