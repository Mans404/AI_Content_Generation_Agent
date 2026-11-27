"""Add autopilot run tables and the image-budget ledger."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "973a73d1f529"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACTIVE = "status IN ('queued', 'running', 'needs_attention')"


def upgrade() -> None:
    op.create_table(
        "autopilot_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("month_key", sa.String(length=7), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("ideas_id", sa.Uuid(), nullable=True),
        sa.Column("planned_posts", sa.Integer(), nullable=False),
        sa.Column("planned_images", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ideas_id"], ["ideas.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "idempotency_key"),
    )
    op.create_index("ix_autopilot_runs_owner_id", "autopilot_runs", ["owner_id"])
    op.create_index(
        "uq_autopilot_runs_one_active_per_owner",
        "autopilot_runs",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE),
    )
    op.create_table(
        "autopilot_run_posts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generation_id", sa.Uuid(), nullable=True),
        sa.Column("schedule_id", sa.Uuid(), nullable=True),
        sa.Column("image_state", sa.String(length=16), nullable=False),
        sa.Column("post_state", sa.String(length=24), nullable=False),
        sa.Column("error", sa.String(length=1024), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["autopilot_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generation_id"], ["design_image_generations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["schedule_id"], ["facebook_post_schedules.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "position"),
    )

    op.create_table(
        "autopilot_image_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("month_key", sa.String(length=7), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("post_position", sa.Integer(), nullable=True),
        sa.Column("generation_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["autopilot_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_autopilot_image_ledger_owner_month",
        "autopilot_image_ledger",
        ["owner_id", "month_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_autopilot_image_ledger_owner_month", table_name="autopilot_image_ledger")
    op.drop_table("autopilot_image_ledger")
    op.drop_table("autopilot_run_posts")
    op.drop_index("uq_autopilot_runs_one_active_per_owner", table_name="autopilot_runs")
    op.drop_index("ix_autopilot_runs_owner_id", table_name="autopilot_runs")
    op.drop_table("autopilot_runs")