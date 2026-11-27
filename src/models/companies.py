from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (
    DateTime,
    Enum as SQLAlchemyEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    text,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from src.models.enums import DoctorLanguage, DoctorSpecialization


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

class DoctorModel(Base):
    __tablename__ = "companies"
    __table_args__ = (
        Index("ix_companies_owner_id", "owner_id"),
        UniqueConstraint("owner_id", name="uq_companies_owner_id"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    owner_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[DoctorLanguage] = mapped_column(
        default=DoctorLanguage.EN,
        nullable=False,
    )
    picture_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    doctor_specialization: Mapped[DoctorSpecialization] = mapped_column(
    SQLAlchemyEnum(
        DoctorSpecialization,
        name="DoctorSpecialization",
        values_callable=lambda enum_cls: [
            member.value for member in enum_cls
        ],
    ),
    default=DoctorSpecialization.OTHER,
    nullable=False,
    )
    audiences: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    types_of_medical_procedures: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    strengths: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    posts_per_week: Mapped[int] = mapped_column(
        nullable=False,
        default=3,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class MonthlyIdeasModel(Base):
    __tablename__ = "monthly_ideas"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "month_start",
            name="uq_monthly_ideas_company_month",
        ),
        Index("ix_monthly_ideas_company_id", "company_id"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    month_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    doctor_offers: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    advice_and_matters_that_most_people_find_confusing: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class IdeasModel(Base):
    __tablename__ = "ideas"
    __table_args__ = (
        Index("ix_ideas_company_id", "company_id"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    ideas: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    post_types: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    design_prompts: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    captions: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class DesignImageModel(Base):
    __tablename__ = "design_images"
    __table_args__ = (
        UniqueConstraint("ideas_id", "prompt_index"),
        Index("ix_design_images_company_id", "company_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    ideas_id: Mapped[UUID] = mapped_column(
        ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False
    )
    prompt_index: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DesignImageGenerationModel(Base):
    __tablename__ = "design_image_generations"
    __table_args__ = (
        UniqueConstraint("ideas_id", "prompt_index"),
        Index("ix_design_image_generations_company_id", "company_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    ideas_id: Mapped[UUID] = mapped_column(
        ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False
    )
    prompt_index: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    stored: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FacebookPostScheduleModel(Base):
    __tablename__ = "facebook_post_schedules"
    __table_args__ = (
        Index("ix_facebook_post_schedules_owner_id", "owner_id"),
        Index("ix_facebook_post_schedules_generation_id", "generation_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    ideas_id: Mapped[UUID] = mapped_column(
        ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False
    )
    generation_id: Mapped[UUID] = mapped_column(
        ForeignKey("design_image_generations.id", ondelete="CASCADE"), nullable=False
    )
    caption: Mapped[str] = mapped_column(String(63206), nullable=False)
    image_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    facebook_post_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="preview")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

#######
class TelegramPostReviewModel(Base):
    """Approval state for one scheduled post in the Telegram review flow.

    One row per schedule that goes through Telegram approval. Existing
    remote Facebook schedules never get a row here, and this table never
    modifies their tracking.

    Status lifecycle (design intent - enforced by code added in later
    steps, not by this table alone):
      pending -> sending -> awaiting_approval -> approved -> publishing
      -> published. rejected goes back to sending with a regenerated
      image. failed is terminal. needs_attention marks uncertain
      outcomes (the message/post may already exist remotely) and is
      never auto-retried. awaiting_approval never publishes on its own:
      silence means no post. Transitions use conditional UPDATEs so
      exactly one worker wins each claim.
    """

    __tablename__ = "telegram_post_reviews"
    __table_args__ = (
        UniqueConstraint("schedule_id"),
        Index("ix_telegram_post_reviews_owner_id", "owner_id"),
        Index("ix_telegram_post_reviews_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    schedule_id: Mapped[UUID] = mapped_column(
        ForeignKey("facebook_post_schedules.id", ondelete="CASCADE"), nullable=False
    )
    generation_id: Mapped[UUID] = mapped_column(
        ForeignKey("design_image_generations.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    telegram_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sent_image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    sent_caption: Mapped[str | None] = mapped_column(String(63206), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

#######
class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)


class RevokedTokenModel(Base):
    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

class AutopilotRunModel(Base):
    """One one-shot autopilot run: plan -> prompts -> captions -> images ->
    store -> schedule (always live=true with a future time, so every post
    goes through Telegram review).

    status: queued -> running -> completed | partial | failed | cancelled,
    or needs_attention (a paid step may or may not have happened; never
    auto-retried). stage records the last finished step so a restart
    resumes instead of paying twice.
    """

    __tablename__ = "autopilot_runs"
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key"),
        Index("ix_autopilot_runs_owner_id", "owner_id"),
        Index(
            "uq_autopilot_runs_one_active_per_owner",
            "owner_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running', 'needs_attention')"),
            sqlite_where=text("status IN ('queued', 'running', 'needs_attention')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    month_key: Mapped[str] = mapped_column(String(7), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    ideas_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ideas.id", ondelete="SET NULL"), nullable=True
    )
    planned_posts: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_images: Mapped[int] = mapped_column(Integer, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

class AutopilotRunPostModel(Base):
    """One post of a run: its client-chosen time and its progress."""

    __tablename__ = "autopilot_run_posts"
    __table_args__ = (UniqueConstraint("run_id", "position"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("autopilot_runs.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    generation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("design_image_generations.id", ondelete="SET NULL"), nullable=True
    )
    schedule_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("facebook_post_schedules.id", ondelete="SET NULL"), nullable=True
    )
    image_state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    post_state: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class AutopilotImageLedgerModel(Base):
    """Signed image-budget ledger. kind: reserve (+n at run creation),
    release (-n of an unused reservation), spend (+1 per generated initial
    image), regen (+1 per paid regeneration, one per generation_id).
    Used = sum(spend); reserved = sum(reserve+release); regens = sum(regen)."""

    __tablename__ = "autopilot_image_ledger"
    __table_args__ = (Index("ix_autopilot_image_ledger_owner_month", "owner_id", "month_key"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    month_key: Mapped[str] = mapped_column(String(7), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("autopilot_runs.id", ondelete="SET NULL"), nullable=True
    )
    post_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )