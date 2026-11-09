"""Phase 11 Trainer network: app_user, auth_session, rate_limit_hit, trainer_profile,
trainer_topic, cv_document, network_invite, trainer_tag, admin_note; ai_usage.workshop_id
becomes nullable and gains cv_document_id / opportunity_id (spec/data-model.md §Phase 11).

Revision ID: 0006
Revises: 0005
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels = None
depends_on = None


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("oidc_issuer", sa.String(200), nullable=True),
        sa.Column("oidc_subject", sa.String(255), nullable=True),
        _ts("created_at"),
        _ts("last_login_at", nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_user")),
        sa.UniqueConstraint("email", name=op.f("uq_app_user_email")),
        sa.UniqueConstraint("oidc_issuer", "oidc_subject", name="uq_app_user_oidc_issuer_subject"),
    )

    op.create_table(
        "auth_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        _ts("created_at"),
        _ts("expires_at"),
        _ts("last_seen_at"),
        _ts("revoked_at", nullable=True),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"],
            name=op.f("fk_auth_session_user_id_app_user"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_session")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_session_token_hash")),
    )
    op.create_index("ix_auth_session_user_id", "auth_session", ["user_id"])

    op.create_table(
        "rate_limit_hit",
        sa.Column("bucket", sa.String(120), nullable=False),
        _ts("window_start"),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("bucket", "window_start", name=op.f("pk_rate_limit_hit")),
    )

    op.create_table(
        "trainer_profile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("headline", sa.String(160), nullable=False),
        sa.Column("bio_md", sa.Text(), nullable=False, server_default=""),
        sa.Column("city", sa.String(80), nullable=True),
        sa.Column("remote_ok", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("linkedin_url", sa.String(300), nullable=True),
        sa.Column("github_url", sa.String(300), nullable=True),
        sa.Column("website_url", sa.String(300), nullable=True),
        sa.Column("past_work_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("rate_min", sa.Integer(), nullable=True),
        sa.Column("rate_max", sa.Integer(), nullable=True),
        sa.Column("rate_currency", sa.String(3), nullable=True),
        sa.Column("rate_unit", sa.String(8), nullable=True),
        sa.Column("pro_bono", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("availability_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("available_from", sa.Date(), nullable=True),
        sa.Column("blackout_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="private"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        _ts("verified_at", nullable=True),
        sa.Column("verified_by", sa.String(254), nullable=True),
        _ts("consent_at"),
        sa.Column("consent_version", sa.String(16), nullable=False),
        sa.Column("autofilled_fields_json", sa.Text(), nullable=False, server_default="[]"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"],
            name=op.f("fk_trainer_profile_user_id_app_user"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trainer_profile")),
        sa.UniqueConstraint("user_id", name=op.f("uq_trainer_profile_user_id")),
    )

    op.create_table(
        "trainer_topic",
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["trainer_profile.id"],
            name=op.f("fk_trainer_topic_profile_id_trainer_profile"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"], ["topic.id"],
            name=op.f("fk_trainer_topic_topic_id_topic"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("profile_id", "topic_id", name=op.f("pk_trainer_topic")),
    )

    op.create_table(
        "cv_document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("original_filename", sa.String(200), nullable=True),
        sa.Column("storage_key", sa.String(300), nullable=True),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("text_extract", sa.Text(), nullable=False, server_default=""),
        sa.Column("draft_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("draft_json", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"],
            name=op.f("fk_cv_document_user_id_app_user"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cv_document")),
        sa.UniqueConstraint("user_id", name=op.f("uq_cv_document_user_id")),
    )

    op.create_table(
        "network_invite",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(43), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("name", sa.String(120), nullable=True),
        sa.Column("created_by", sa.String(254), nullable=False),
        _ts("created_at"),
        _ts("expires_at"),
        _ts("accepted_at", nullable=True),
        sa.Column("accepted_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["accepted_user_id"], ["app_user.id"],
            name=op.f("fk_network_invite_accepted_user_id_app_user"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_network_invite")),
        sa.UniqueConstraint("token", name=op.f("uq_network_invite_token")),
    )

    op.create_table(
        "trainer_tag",
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["trainer_profile.id"],
            name=op.f("fk_trainer_tag_profile_id_trainer_profile"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("profile_id", "tag", name=op.f("pk_trainer_tag")),
    )

    op.create_table(
        "admin_note",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author", sa.String(254), nullable=False),
        _ts("created_at"),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["trainer_profile.id"],
            name=op.f("fk_admin_note_profile_id_trainer_profile"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_note")),
    )

    with op.batch_alter_table("ai_usage") as batch:
        batch.alter_column("workshop_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("cv_document_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("opportunity_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_ai_usage_cv_document_id_cv_document", "cv_document",
            ["cv_document_id"], ["id"], ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_ai_usage_opportunity_id_opportunity", "opportunity",
            ["opportunity_id"], ["id"], ondelete="SET NULL",
        )


def downgrade() -> None:
    # Network ai_usage rows have no workshop; they cannot survive workshop_id NOT NULL.
    op.execute("DELETE FROM ai_usage WHERE workshop_id IS NULL")
    with op.batch_alter_table("ai_usage") as batch:
        batch.drop_constraint("fk_ai_usage_opportunity_id_opportunity", type_="foreignkey")
        batch.drop_constraint("fk_ai_usage_cv_document_id_cv_document", type_="foreignkey")
        batch.drop_column("opportunity_id")
        batch.drop_column("cv_document_id")
        batch.alter_column("workshop_id", existing_type=sa.Integer(), nullable=False)

    op.drop_table("admin_note")
    op.drop_table("trainer_tag")
    op.drop_table("network_invite")
    op.drop_table("cv_document")
    op.drop_table("trainer_topic")
    op.drop_table("trainer_profile")
    op.drop_table("rate_limit_hit")
    op.drop_index("ix_auth_session_user_id", table_name="auth_session")
    op.drop_table("auth_session")
    op.drop_table("app_user")
