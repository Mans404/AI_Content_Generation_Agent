"""many changes

Revision ID: 73a21b660044
Revises: fb1010331a9a
Create Date: 2026-10-27 11:25:34.578300
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "73a21b660044"
down_revision: Union[str, Sequence[str], None] = "fb1010331a9a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SPECIALIZATION_VALUES = (
    "internal_medicine",
    "dentistry",
    "dermatology",
    "cardiology",
    "neurology",
    "pediatrics",
    "orthopedics",
    "ophthalmology",
    "obstetrics_and_gynecology",
    "urology",
    "general_surgery",
    "psychiatry",
    "ent",
    "physiotherapy",
    "other",
)

# create_type=False -> we create/drop it explicitly below, never implicitly.
doctor_specialization_enum = postgresql.ENUM(
    *SPECIALIZATION_VALUES,
    name="DoctorSpecialization",
    create_type=False,
)

company_industry_enum = postgresql.ENUM(
    "technology",
    "healthcare",
    "education",
    "finance",
    "real_estate",
    "retail",
    "food_and_beverage",
    "manufacturing",
    "construction",
    "marketing",
    "travel_and_tourism",
    "automotive",
    "telecommunications",
    "logistics",
    "agriculture",
    "other",
    name="companyindustry",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()

    # 1. Create the new enum type, then add the column as nullable.
    doctor_specialization_enum.create(bind, checkfirst=True)

    op.add_column(
        "companies",
        sa.Column(
            "doctor_specialization",
            doctor_specialization_enum,
            nullable=True,
        ),
    )

    # 2. Preserve existing industry values where they match, else 'other'.
    values_sql = ", ".join(f"'{v}'" for v in SPECIALIZATION_VALUES)
    op.execute(
        f"""
        UPDATE companies
        SET doctor_specialization = CASE
            WHEN industry::text IN ({values_sql})
            THEN industry::text::"DoctorSpecialization"
            ELSE 'other'::"DoctorSpecialization"
        END
        """
    )

    op.alter_column(
        "companies",
        "doctor_specialization",
        existing_type=doctor_specialization_enum,
        nullable=False,
    )

    # 3. Rename the language enum type in place (values and data preserved).
    op.execute('ALTER TYPE companylanguage RENAME TO "Doctorlanguage"')

    # 4. Remove the old industry column.
    op.drop_column("companies", "industry")


def downgrade() -> None:
    """Downgrade schema."""

    bind = op.get_bind()

    # 1. Recreate the old industry enum + column.
    company_industry_enum.create(bind, checkfirst=True)

    op.add_column(
        "companies",
        sa.Column("industry", company_industry_enum, nullable=True),
    )

    # The original industry values can't be recovered from specialization
    # (the enums don't overlap), so fall back to 'other'.
    op.execute("UPDATE companies SET industry = 'other'::companyindustry")

    op.alter_column(
        "companies",
        "industry",
        existing_type=company_industry_enum,
        nullable=False,
    )

    # 2. Rename the language enum type back.
    op.execute('ALTER TYPE "Doctorlanguage" RENAME TO companylanguage')

    # 3. Drop the new column, then its enum type.
    op.drop_column("companies", "doctor_specialization")
    doctor_specialization_enum.drop(bind, checkfirst=True)