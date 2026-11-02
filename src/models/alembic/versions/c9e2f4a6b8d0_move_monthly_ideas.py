"""Move doctor offers and confusing matters to monthly ideas."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9e2f4a6b8d0"
down_revision: Union[str, Sequence[str], None] = (
    "7f8e9a0b1c2d",
    "8d2e4f6a1b3c",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "monthly_ideas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("month_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("doctor_offers", sa.JSON(), nullable=False),
        sa.Column(
            "advice_and_matters_that_most_people_find_confusing",
            sa.JSON(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "month_start",
            name="uq_monthly_ideas_company_month",
        ),
    )
    op.create_index(
        "ix_monthly_ideas_company_id",
        "monthly_ideas",
        ["company_id"],
    )
    op.execute(
        """
        INSERT INTO monthly_ideas (
            id,
            company_id,
            month_start,
            doctor_offers,
            advice_and_matters_that_most_people_find_confusing
        )
        SELECT
            gen_random_uuid(),
            id,
            date_trunc(
                'month',
                created_at AT TIME ZONE 'UTC'
            ) AT TIME ZONE 'UTC',
            doctor_offers,
            advice_and_matters_that_most_people_find_confusing
        FROM companies
        """
    )
    op.drop_column("companies", "advice_and_matters_that_most_people_find_confusing")
    op.drop_column("companies", "doctor_offers")


def downgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "doctor_offers",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "companies",
        sa.Column(
            "advice_and_matters_that_most_people_find_confusing",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.execute(
        """
        UPDATE companies
        SET
            doctor_offers = latest.doctor_offers,
            advice_and_matters_that_most_people_find_confusing =
                latest.advice_and_matters_that_most_people_find_confusing
        FROM (
            SELECT DISTINCT ON (company_id)
                company_id,
                doctor_offers,
                advice_and_matters_that_most_people_find_confusing
            FROM monthly_ideas
            ORDER BY company_id, month_start DESC
        ) AS latest
        WHERE companies.id = latest.company_id
        """
    )
    op.drop_index("ix_monthly_ideas_company_id", table_name="monthly_ideas")
    op.drop_table("monthly_ideas")
