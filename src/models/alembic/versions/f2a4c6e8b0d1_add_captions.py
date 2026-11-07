"""Store generated captions with ideas batches."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a4c6e8b0d1"
down_revision: Union[str, Sequence[str], None] = "d8e5f3a1b7c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ideas",
        sa.Column(
            "captions",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.alter_column("ideas", "captions", server_default=None)


def downgrade() -> None:
    op.drop_column("ideas", "captions")
