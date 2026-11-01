"""merge existing migration heads

Revision ID: 8d2e4f6a1b3c
Revises: 3b7c9d1e5f20, 7c1d9e2f4a6b
"""
from typing import Sequence, Union


revision: str = "8d2e4f6a1b3c"
down_revision: Union[str, Sequence[str], None] = (
    "3b7c9d1e5f20",
    "7c1d9e2f4a6b",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
