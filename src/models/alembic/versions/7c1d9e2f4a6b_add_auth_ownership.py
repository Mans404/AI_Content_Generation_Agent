"""add users and company ownership

Revision ID: 7c1d9e2f4a6b
Revises: 09cfdb09463c
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c1d9e2f4a6b"
down_revision: Union[str, Sequence[str], None] = "09cfdb09463c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_name", sa.String(length=255), nullable=False),
        sa.Column("password", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_name"),
    )
    op.add_column(
        "companies",
        sa.Column("owner_id", sa.Uuid(), nullable=True),
    )
    op.create_index("ix_companies_owner_id", "companies", ["owner_id"])
    op.create_foreign_key(
        "fk_companies_owner_id_users",
        "companies",
        "users",
        ["owner_id"],
        ["id"],
    )
    op.create_table(
        "revoked_tokens",
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("jti"),
    )


def downgrade() -> None:
    op.drop_table("revoked_tokens")
    op.drop_constraint("fk_companies_owner_id_users", "companies", type_="foreignkey")
    op.drop_index("ix_companies_owner_id", table_name="companies")
    op.drop_column("companies", "owner_id")
    op.drop_table("users")
