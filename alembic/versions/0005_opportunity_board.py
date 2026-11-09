"""Phase 10 Opportunity Board: topic (+40-topic seed), opportunity, opportunity_topic,
and facilitator_action.subject_type / subject_id.

Revision ID: 0005
Revises: 0004
"""

from datetime import datetime, timezone
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels = None
depends_on = None

# spec/data-model.md §topic — positions 0–39 in exactly this order (5 categories × 8).
TOPIC_SEED: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Languages",
        [
            ("python", "Python"),
            ("javascript", "JavaScript"),
            ("typescript", "TypeScript"),
            ("java", "Java"),
            ("go", "Go"),
            ("rust", "Rust"),
            ("dotnet", "C# / .NET"),
            ("kotlin", "Kotlin"),
        ],
    ),
    (
        "Web & Mobile",
        [
            ("react", "React"),
            ("nextjs", "Next.js"),
            ("nodejs", "Node.js"),
            ("angular", "Angular"),
            ("vuejs", "Vue.js"),
            ("flutter", "Flutter"),
            ("android", "Android"),
            ("ios-swift", "iOS / Swift"),
        ],
    ),
    (
        "AI & Data",
        [
            ("machine-learning", "Machine Learning"),
            ("deep-learning", "Deep Learning"),
            ("generative-ai", "Generative AI & LLMs"),
            ("agentic-ai", "Agentic AI (LangChain / LangGraph)"),
            ("prompt-engineering", "Prompt Engineering"),
            ("data-engineering", "Data Engineering"),
            ("sql-analytics", "SQL & Data Analysis"),
            ("mlops", "MLOps"),
        ],
    ),
    (
        "Cloud & DevOps",
        [
            ("aws", "AWS"),
            ("gcp", "Google Cloud"),
            ("azure", "Azure"),
            ("docker", "Docker"),
            ("kubernetes", "Kubernetes"),
            ("ci-cd", "CI/CD"),
            ("terraform", "Terraform"),
            ("linux", "Linux"),
        ],
    ),
    (
        "Engineering Practice",
        [
            ("system-design", "System Design"),
            ("apis-microservices", "APIs & Microservices"),
            ("testing-qa", "Testing & QA"),
            ("git-github", "Git & GitHub"),
            ("cybersecurity", "Cybersecurity"),
            ("agile-scrum", "Agile & Scrum"),
            ("product-management", "Product Management"),
            ("ux-design", "UI / UX Design"),
        ],
    ),
]


def seed_rows(now: datetime) -> list[dict]:
    rows: list[dict] = []
    for category, topics in TOPIC_SEED:
        for slug, name in topics:
            rows.append(
                {
                    "slug": slug,
                    "name": name,
                    "category": category,
                    "position": len(rows),
                    "active": True,
                    "created_at": now,
                    "updated_at": now,
                }
            )
    return rows


def upgrade() -> None:
    topic = op.create_table(
        "topic",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(48), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("category", sa.String(48), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_topic")),
        sa.UniqueConstraint("slug", name=op.f("uq_topic_slug")),
        sa.UniqueConstraint("name", name=op.f("uq_topic_name")),
    )

    op.create_table(
        "opportunity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("type", sa.String(24), nullable=False),
        sa.Column("summary", sa.String(280), nullable=False),
        sa.Column("description_md", sa.Text(), nullable=False, server_default=""),
        sa.Column("location_mode", sa.String(16), nullable=False, server_default="remote"),
        sa.Column("city", sa.String(80), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("duration_text", sa.String(80), nullable=True),
        sa.Column("compensation_text", sa.String(120), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("partner_display_name", sa.String(160), nullable=True),
        sa.Column("partner_internal_name", sa.String(160), nullable=True),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity")),
    )
    op.create_index("ix_opportunity_status_deadline", "opportunity", ["status", "deadline"])
    op.create_index("ix_opportunity_published_at", "opportunity", ["published_at"])

    op.create_table(
        "opportunity_topic",
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunity.id"],
            name=op.f("fk_opportunity_topic_opportunity_id_opportunity"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topic.id"],
            name=op.f("fk_opportunity_topic_topic_id_topic"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("opportunity_id", "topic_id", name=op.f("pk_opportunity_topic")),
    )
    op.create_index("ix_opportunity_topic_topic_id", "opportunity_topic", ["topic_id"])

    with op.batch_alter_table("facilitator_action") as batch:
        batch.add_column(sa.Column("subject_type", sa.String(32), nullable=True))
        batch.add_column(sa.Column("subject_id", sa.Integer(), nullable=True))
        batch.create_index(
            "ix_facilitator_action_subject_created",
            ["subject_type", "subject_id", "created_at"],
        )

    op.bulk_insert(topic, seed_rows(datetime.now(timezone.utc)))


def downgrade() -> None:
    with op.batch_alter_table("facilitator_action") as batch:
        batch.drop_index("ix_facilitator_action_subject_created")
        batch.drop_column("subject_id")
        batch.drop_column("subject_type")
    op.drop_index("ix_opportunity_topic_topic_id", table_name="opportunity_topic")
    op.drop_table("opportunity_topic")
    op.drop_index("ix_opportunity_published_at", table_name="opportunity")
    op.drop_index("ix_opportunity_status_deadline", table_name="opportunity")
    op.drop_table("opportunity")
    op.drop_table("topic")
