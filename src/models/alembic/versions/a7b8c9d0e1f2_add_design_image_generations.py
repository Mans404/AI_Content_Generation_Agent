"""Track generated design images before they are stored."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = (
    "f2a4c6e8b0d1",
    "e1f2a3b4c5d6",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "design_image_generations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("ideas_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_index", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("stored", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ideas_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ideas_id", "prompt_index"),
    )
    op.create_index(
        "ix_design_image_generations_company_id",
        "design_image_generations",
        ["company_id"],
    )
    op.alter_column("design_image_generations", "stored", server_default=None)


def downgrade() -> None:
    op.drop_index(
        "ix_design_image_generations_company_id",
        table_name="design_image_generations",
    )
    op.drop_table("design_image_generations")
