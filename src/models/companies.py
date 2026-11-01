from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (
    DateTime,
    Enum as SQLAlchemyEnum,
    ForeignKey,
    Index,
    JSON,
    String,
    UniqueConstraint,
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