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


class CompanyIndustry(str, Enum):
    TECHNOLOGY = "technology"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    FINANCE = "finance"
    REAL_ESTATE = "real_estate"
    RETAIL = "retail"
    FOOD_AND_BEVERAGE = "food_and_beverage"
    MANUFACTURING = "manufacturing"
    CONSTRUCTION = "construction"
    MARKETING = "marketing"
    TRAVEL_AND_TOURISM = "travel_and_tourism"
    AUTOMOTIVE = "automotive"
    TELECOMMUNICATIONS = "telecommunications"
    LOGISTICS = "logistics"
    AGRICULTURE = "agriculture"
    OTHER = "other"


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
    picture_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    industry: Mapped[CompanyIndustry] = mapped_column(
    SQLAlchemyEnum(
        CompanyIndustry,
        name="companyindustry",
        values_callable=lambda enum_cls: [
            member.value for member in enum_cls
        ],
    ),
    default=CompanyIndustry.OTHER,
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