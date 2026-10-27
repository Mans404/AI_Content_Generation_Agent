"""add doctor strengths

Revision ID: 3b7c9d1e5f20
Revises: 26a1cb3395a4
Create Date: 2026-10-27 14:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3b7c9d1e5f20"
down_revision: Union[str, Sequence[str], None] = "26a1cb3395a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "strengths",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )


def downgrade() -> None:
    op.drop_column("companies", "strengths")
