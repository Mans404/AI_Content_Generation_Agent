"""Track Facebook post scheduling requests."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "facebook_post_schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("ideas_id", sa.Uuid(), nullable=False),
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("caption", sa.String(length=63206), nullable=False),
        sa.Column("image_url", sa.String(length=1024), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("facebook_post_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ideas_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["generation_id"],
            ["design_image_generations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_facebook_post_schedules_owner_id",
        "facebook_post_schedules",
        ["owner_id"],
    )
    op.create_index(
        "ix_facebook_post_schedules_generation_id",
        "facebook_post_schedules",
        ["generation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_facebook_post_schedules_generation_id",
        table_name="facebook_post_schedules",
    )
    op.drop_index(
        "ix_facebook_post_schedules_owner_id",
        table_name="facebook_post_schedules",
    )
    op.drop_table("facebook_post_schedules")
