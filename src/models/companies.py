from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, JSON, String, Uuid, func
from sqlalchemy import DateTime, JSON, String, Uuid, func, Enum as SQLAlchemyEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


class DoctorLanguage(str, Enum):
    AR = "AR"
    EN = "EN"


class DoctorSpecialization(str, Enum):
    INTERNAL_MEDICINE = "internal_medicine"
    DENTISTRY = "dentistry"
    DERMATOLOGY = "dermatology"
    CARDIOLOGY = "cardiology"
    NEUROLOGY = "neurology"
    PEDIATRICS = "pediatrics"
    ORTHOPEDICS = "orthopedics"
    OPHTHALMOLOGY = "ophthalmology"
    OBSTETRICS_AND_GYNECOLOGY = "obstetrics_and_gynecology"
    UROLOGY = "urology"
    GENERAL_SURGERY = "general_surgery"
    PSYCHIATRY = "psychiatry"
    ENT = "ent"
    PHYSIOTHERAPY = "physiotherapy"
    OTHER = "other"


class DoctorModel(Base):
    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
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
    posts_per_week: Mapped[int] = mapped_column(
        nullable=False,
        default=3,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )