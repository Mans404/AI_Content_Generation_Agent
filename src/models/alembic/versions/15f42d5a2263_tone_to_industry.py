"""tone to doctor_specialization

Revision ID: 15f42d5a2263
Revises: 4d7594d3b2c1
Create Date: 2026-10-19 18:19:00.813630

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '15f42d5a2263'
down_revision: Union[str, Sequence[str], None] = '4d7594d3b2c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    company_doctor_specialization = postgresql.ENUM(
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
        name="DoctorSpecialization",
        create_type=False,
    )
    bind = op.get_bind()
    company_doctor_specialization.create(bind, checkfirst=True)

    op.add_column(
        "companies",
        sa.Column(
            "doctor_specialization",
            company_doctor_specialization,
            nullable=False,
            server_default="other",
        )
    )
    op.alter_column("companies", "doctor_specialization", server_default=None)
    op.drop_column("companies", "tone")


def downgrade() -> None:
    """Downgrade schema."""
    company_tone = postgresql.ENUM(
        "professional",
        "friendly",
        "playful",
        "authoritative",
        "inspirational",
        name="companytone",
        create_type=False,
    )
    bind = op.get_bind()
    company_tone.create(bind, checkfirst=True)

    op.add_column(
        "companies",
        sa.Column(
            "tone",
            company_tone,
            nullable=False,
            server_default="professional",
        )
    )
    op.alter_column("companies", "tone", server_default=None)
    op.drop_column("companies", "doctor_specialization")
