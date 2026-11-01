"""allow one company profile per owner

Revision ID: 7f8e9a0b1c2d
Revises: 26a1cb3395a4
Create Date: 2026-11-01 16:20:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "7f8e9a0b1c2d"
down_revision: Union[str, Sequence[str], None] = "26a1cb3395a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM companies older
        USING companies newer
        WHERE older.owner_id IS NOT NULL
          AND older.owner_id = newer.owner_id
          AND (
              older.created_at < newer.created_at
              OR (
                  older.created_at = newer.created_at
                  AND older.id < newer.id
              )
          )
        """
    )
    op.create_unique_constraint(
        "uq_companies_owner_id",
        "companies",
        ["owner_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_companies_owner_id", "companies", type_="unique")
