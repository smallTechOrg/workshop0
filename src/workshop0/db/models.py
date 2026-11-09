"""All SQLAlchemy models — the FULL v0.2 schema per spec/data-model.md.

Later-phase tables/columns exist from Phase 1 so no mid-season migrate-and-backfill
is ever needed. Portable types only (Integer/String/Text/Boolean/DateTime/Numeric;
JSON stored as Text) — PostgreSQL-ready via DATABASE_URL.
"""

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql.expression import false as sa_false
from sqlalchemy.sql.expression import true as sa_true

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Workshop(Base):
    __tablename__ = "workshop"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    admin_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    join_slug: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="live", index=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grace_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grace_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    join_form_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    stuck_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    cloned_from_id: Mapped[int | None] = mapped_column(
        ForeignKey("workshop.id"), nullable=True, index=True
    )
    agenda_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("agenda_template.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Phase 6 — public self-service creation (migration 0004_public_creation).
    # creator_email is returned on the admin list ONLY; never on a facilitator,
    # participant or public payload.
    creator_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_via: Mapped[str] = mapped_column(
        String(16), nullable=False, default="admin", server_default="admin"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class Milestone(Base):
    __tablename__ = "milestone"
    __table_args__ = (Index("ix_milestone_workshop_id_position", "workshop_id", "position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workshop_id: Mapped[int] = mapped_column(
        ForeignKey("workshop.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Optional per-milestone completion input (JSON: {type,label,options?}).
    # Null ⇒ no input required; see services/milestone_input.py.
    input_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class Participant(Base):
    __tablename__ = "participant"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workshop_id: Mapped[int] = mapped_column(
        ForeignKey("workshop.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    token: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    answers_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class MilestoneCompletion(Base):
    __tablename__ = "milestone_completion"
    __table_args__ = (
        UniqueConstraint("participant_id", "milestone_id", name="uq_completion_participant_milestone"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participant.id", ondelete="CASCADE"), nullable=False, index=True
    )
    milestone_id: Mapped[int] = mapped_column(
        ForeignKey("milestone.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="participant")
    # The value the participant submitted, when the milestone required an input.
    input_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class HelpRequest(Base):
    __tablename__ = "help_request"
    __table_args__ = (
        Index("ix_help_request_workshop_status_created", "workshop_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workshop_id: Mapped[int] = mapped_column(
        ForeignKey("workshop.id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participant.id", ondelete="CASCADE"), nullable=False, index=True
    )
    milestone_id: Mapped[int | None] = mapped_column(
        ForeignKey("milestone.id", ondelete="SET NULL"), nullable=True, index=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    # Who last marked it resolved: "participant" | "facilitator" (null while open).
    resolved_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class HelpAnswer(Base):
    __tablename__ = "help_answer"
    __table_args__ = (
        Index("ix_help_answer_request_created", "help_request_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    help_request_id: Mapped[int] = mapped_column(
        ForeignKey("help_request.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    answer_md: Mapped[str] = mapped_column(Text, nullable=False)
    draft: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ai_context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Broadcast(Base):
    __tablename__ = "broadcast"
    __table_args__ = (Index("ix_broadcast_workshop_cleared", "workshop_id", "cleared_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workshop_id: Mapped[int] = mapped_column(
        ForeignKey("workshop.id", ondelete="CASCADE"), nullable=False
    )
    message_md: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FacilitatorAction(Base):
    __tablename__ = "facilitator_action"
    __table_args__ = (
        Index("ix_facilitator_action_workshop_created", "workshop_id", "created_at"),
        Index(
            "ix_facilitator_action_subject_created", "subject_type", "subject_id", "created_at"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workshop_id: Mapped[int | None] = mapped_column(
        ForeignKey("workshop.id", ondelete="CASCADE"), nullable=True
    )
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    undo_data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Phase 10 (migration 0005): admin-console rows carry the subject they act on
    # (`opportunity` | `topic`; later phases add more). No FK — the audit row
    # outlives its subject. Null for every workshop-scoped row.
    subject_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subject_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )


class AgendaTemplate(Base):
    __tablename__ = "agenda_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class AgendaTemplateMilestone(Base):
    __tablename__ = "agenda_template_milestone"
    __table_args__ = (
        Index("ix_agenda_template_milestone_template_position", "template_id", "position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("agenda_template.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)


class JoinFormTemplate(Base):
    __tablename__ = "join_form_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    fields_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class AiUsage(Base):
    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_workshop_created", "workshop_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Nullable from Phase 11 (0006): network rows (profile_draft, shortlist_rank) have no
    # workshop. Network spend = SUM(cost_usd) WHERE workshop_id IS NULL.
    workshop_id: Mapped[int | None] = mapped_column(
        ForeignKey("workshop.id", ondelete="CASCADE"), nullable=True
    )
    help_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("help_request.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cv_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("cv_document.id", ondelete="SET NULL"), nullable=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunity.id", ondelete="SET NULL"), nullable=True
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)  # triage_answer|profile_draft|opportunity_draft|shortlist_rank
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


# --------------------------------------------------------------------------- Phase 10
# Opportunity Board (migration 0005_opportunity_board) — spec/data-model.md §Phase 10.


class Topic(Base):
    """Curated, admin-maintained taxonomy. `slug` is immutable (public filter URLs)."""

    __tablename__ = "topic"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(48), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa_true()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class Partner(Base):
    """Admin-managed partner list (migration 0007, spec/data-model.md §Phase 11b).
    `name_key` = casefold of the whitespace-collapsed internal_name (unique). Admin-only."""

    __tablename__ = "partner"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    internal_name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa_true()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class Opportunity(Base):
    """One admin-curated listing. `status` is the STORED status (draft|open|closed);
    the effective status (adds `expired`) is computed on read — see
    services/opportunities.py::effective_status. `partner_internal_name` and
    `internal_notes` are admin-only and never serialized publicly."""

    __tablename__ = "opportunity"
    __table_args__ = (
        Index("ix_opportunity_status_deadline", "status", "deadline"),
        Index("ix_opportunity_published_at", "published_at"),
        Index("ix_opportunity_partner_id", "partner_id"),
        UniqueConstraint("slug", name="uq_opportunity_slug"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Phase 11e: public URL key, server-generated (services/slugs.py); frozen on first publish.
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    type: Mapped[str] = mapped_column(String(24), nullable=False)
    summary: Mapped[str] = mapped_column(String(280), nullable=False)
    description_md: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    location_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="remote", server_default="remote"
    )
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)  # mirror of locations[0].city
    # JSON list of {"city", "country"}; parsed via services/locations.parse_stored
    locations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    duration_text: Mapped[str | None] = mapped_column(String(80), nullable=True)
    compensation_text: Mapped[str | None] = mapped_column(String(120), nullable=True)  # optional note
    compensation_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compensation_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compensation_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)  # INR|USD
    compensation_unit: Mapped[str | None] = mapped_column(String(8), nullable=True)  # hour|day|course|month
    partner_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("partner.id", ondelete="RESTRICT"), nullable=True
    )  # admin-only, never public
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    partner_display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    partner_internal_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class OpportunityTopic(Base):
    __tablename__ = "opportunity_topic"
    __table_args__ = (Index("ix_opportunity_topic_topic_id", "topic_id"),)

    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunity.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topic.id", ondelete="RESTRICT"), primary_key=True
    )


# --------------------------------------------------------------------------- Phase 11
# Trainer network (migration 0006_trainer_network) — spec/data-model.md §Phase 11.


class AppUser(Base):
    """A network account (OIDC-shaped). No role column: admin-ness is derived per request
    (`email_verified and email in WORKSHOP0_ADMIN_EMAILS`)."""

    __tablename__ = "app_user"
    __table_args__ = (
        UniqueConstraint("oidc_issuer", "oidc_subject", name="uq_app_user_oidc_issuer_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    oidc_issuer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    oidc_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthSession(Base):
    """`token_hash` = SHA-256 hex of the `workshop0_session` cookie value; the raw token
    is never stored."""

    __tablename__ = "auth_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)


class RateLimitHit(Base):
    """Stateless fixed-window limiter row; the DB is the only state shared by instances."""

    __tablename__ = "rate_limit_hit"

    bucket: Mapped[str] = mapped_column(String(120), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


class TrainerProfile(Base):
    """1:1 with app_user; live the moment it is saved. `rate_*` are admin-only (never in a
    non-admin payload except the owner's own profile)."""

    __tablename__ = "trainer_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    headline: Mapped[str] = mapped_column(String(160), nullable=False)
    bio_md: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    remote_ok: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa_true()
    )
    linkedin_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    past_work_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    rate_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    rate_unit: Mapped[str | None] = mapped_column(String(8), nullable=True)
    pro_bono: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_false()
    )
    availability_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    available_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    blackout_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default="private", server_default="private"
    )
    verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_false()
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(16), nullable=False)
    autofilled_fields_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class TrainerTopic(Base):
    __tablename__ = "trainer_topic"

    profile_id: Mapped[int] = mapped_column(
        ForeignKey("trainer_profile.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topic.id", ondelete="RESTRICT"), primary_key=True
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False)  # intermediate|advanced|expert


class CvDocument(Base):
    """The trainer's current CV — exactly one per user; a new upload replaces it."""

    __tablename__ = "cv_document"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # pdf|docx|text
    original_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    text_extract: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    draft_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )  # pending|ready|failed|skipped
    draft_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class NetworkInvite(Base):
    __tablename__ = "network_invite"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(43), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    # Phase 11d (0009_invite_revoke): set once by an admin Revoke; never on an accepted invite.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(254), nullable=True)


class TrainerTag(Base):
    """Admin-private tag (lower-cased, `^[a-z0-9][a-z0-9 -]{0,39}$`, ≤20 per trainer)."""

    __tablename__ = "trainer_tag"

    profile_id: Mapped[int] = mapped_column(
        ForeignKey("trainer_profile.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String(40), primary_key=True)


class AdminNote(Base):
    """Admin-private plain-text note on a trainer."""

    __tablename__ = "admin_note"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("trainer_profile.id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
