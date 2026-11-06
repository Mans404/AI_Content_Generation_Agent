"""Store prompts generated for the design language model."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8e5f3a1b7c9"
down_revision: Union[str, Sequence[str], None] = "b7c4d2e9f1a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ideas",
        sa.Column(
            "design_prompts",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.alter_column("ideas", "design_prompts", server_default=None)


def downgrade() -> None:
    op.drop_column("ideas", "design_prompts")
