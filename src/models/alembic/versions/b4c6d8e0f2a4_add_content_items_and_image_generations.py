"""Add content items and image generation review records."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b4c6d8e0f2a4"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


content_item_status_enum = postgresql.ENUM(
    "idea_generated",
    "prompt_generated",
    "caption_generated",
    "image_generated",
    "image_stored",
    name="contentitemstatus",
    create_type=False,
)

image_generation_status_enum = postgresql.ENUM(
    "pending_review",
    "approved",
    "rejected",
    name="imagegenerationstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    content_item_status_enum.create(bind, checkfirst=True)
    image_generation_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "content_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("idea", sa.Text(), nullable=False),
        sa.Column("post_type", sa.String(length=255), nullable=False),
        sa.Column("design_prompt", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column(
            "status",
            content_item_status_enum,
            server_default=sa.text("'idea_generated'"),
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "position"),
    )
    op.create_index(
        "ix_content_items_company_id",
        "content_items",
        ["company_id"],
    )
    op.create_index(
        "ix_content_items_batch_id",
        "content_items",
        ["batch_id"],
    )
    op.alter_column("content_items", "status", server_default=None)
    op.alter_column("content_items", "attempts", server_default=None)

    op.create_table(
        "image_generations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("content_item_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("temp_path", sa.String(length=1024), nullable=False),
        sa.Column("final_path", sa.String(length=1024), nullable=True),
        sa.Column(
            "status",
            image_generation_status_enum,
            server_default=sa.text("'pending_review'"),
            nullable=False,
        ),
        sa.Column("review_feedback", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["content_item_id"],
            ["content_items.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_image_generations_content_item_id",
        "image_generations",
        ["content_item_id"],
    )
    op.alter_column("image_generations", "status", server_default=None)


def downgrade() -> None:
    op.drop_index(
        "ix_image_generations_content_item_id",
        table_name="image_generations",
    )
    op.drop_table("image_generations")
    op.drop_index("ix_content_items_batch_id", table_name="content_items")
    op.drop_index("ix_content_items_company_id", table_name="content_items")
    op.drop_table("content_items")

    bind = op.get_bind()
    image_generation_status_enum.drop(bind, checkfirst=True)
    content_item_status_enum.drop(bind, checkfirst=True)
