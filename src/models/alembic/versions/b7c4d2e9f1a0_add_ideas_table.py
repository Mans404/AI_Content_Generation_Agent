"""Store generated ideas and post types."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c4d2e9f1a0"
down_revision: Union[str, Sequence[str], None] = "c9e2f4a6b8d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ideas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("ideas", sa.JSON(), nullable=False),
        sa.Column("post_types", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ideas_company_id", "ideas", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_ideas_company_id", table_name="ideas")
    op.drop_table("ideas")
