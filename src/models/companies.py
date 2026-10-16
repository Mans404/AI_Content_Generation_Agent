from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, JSON, String, Uuid, func
from sqlalchemy import DateTime, JSON, String, Uuid, func, Enum as SQLAlchemyEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


class CompanyLanguage(str, Enum):
    AR = "AR"
    EN = "EN"


class CompanyTone(str, Enum):
    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"
    PLAYFUL = "playful"
    AUTHORITATIVE = "authoritative"
    INSPIRATIONAL = "inspirational"


class CompanyModel(Base):
    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[CompanyLanguage] = mapped_column(
        default=CompanyLanguage.EN,
        nullable=False,
    )
    logo_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    primary_color: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="#000000",
    )
    secondary_color: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="#FFFFFF",
    )
    tone: Mapped[CompanyTone] = mapped_column(
    SQLAlchemyEnum(
        CompanyTone,
        name="companytone",
        values_callable=lambda enum_cls: [
            member.value for member in enum_cls
        ],
    ),
    default=CompanyTone.PROFESSIONAL,
    nullable=False,
    )
    audiences: Mapped[list[str]] = mapped_column(
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