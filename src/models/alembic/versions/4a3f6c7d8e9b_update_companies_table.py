"""Update companies table to the company profile schema.

Revision ID: 4a3f6c7d8e9b
Revises: 0be0239c931e
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4a3f6c7d8e9b"
down_revision: Union[str, Sequence[str], None] = "0be0239c931e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


language_enum = sa.Enum("AR", "EN", name="companylanguage")
tone_enum = sa.Enum(
    "professional",
    "friendly",
    "playful",
    "authoritative",
    "inspirational",
    name="companytone",
)



def upgrade() -> None:
    """Apply the company profile schema."""
    bind = op.get_bind()

    # Rename the existing table first.
    op.rename_table("company_model", "companies")

    language_enum.create(bind, checkfirst=True)
    tone_enum.create(bind, checkfirst=True)

    op.alter_column("companies", "company_id", new_column_name="id")
    op.alter_column("companies", "company", new_column_name="name")
    op.alter_column(
        "companies",
        "reference_design_path",
        new_column_name="logo_path",
    )

    op.execute(
        sa.text(
            "UPDATE companies SET logo_path = '' "
            "WHERE logo_path IS NULL"
        )
    )
    op.alter_column("companies", "logo_path", nullable=False)

    op.add_column(
        "companies",
        sa.Column(
            "language",
            language_enum,
            nullable=False,
            server_default="EN",
        ),
    )
    op.add_column(
        "companies",
        sa.Column(
            "primary_color",
            sa.String(length=32),
            nullable=False,
            server_default="#000000",
        ),
    )
    op.add_column(
        "companies",
        sa.Column(
            "secondary_color",
            sa.String(length=32),
            nullable=False,
            server_default="#FFFFFF",
        ),
    )
    op.add_column(
        "companies",
        sa.Column(
            "tone",
            tone_enum,
            nullable=False,
            server_default="professional",
        ),
    )
    op.add_column(
        "companies",
        sa.Column(
            "audiences",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "companies",
        sa.Column(
            "posts_per_week",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )

    op.drop_column("companies", "ideas")
    op.drop_column("companies", "post_types")
    op.drop_column("companies", "company_theme")
    op.drop_column("companies", "industry")
    op.drop_column("companies", "updated_at")

    op.alter_column("companies", "language", server_default=None)
    op.alter_column("companies", "primary_color", server_default=None)
    op.alter_column("companies", "secondary_color", server_default=None)
    op.alter_column("companies", "tone", server_default=None)
    op.alter_column("companies", "audiences", server_default=None)
    op.alter_column("companies", "posts_per_week", server_default=None)



def downgrade() -> None:
    """Restore the legacy companies table shape."""
    op.add_column(
        "companies",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("companies", sa.Column("industry", sa.String(length=255)))
    op.add_column("companies", sa.Column("company_theme", sa.Text()))
    op.add_column("companies", sa.Column("post_types", sa.JSON()))
    op.add_column("companies", sa.Column("ideas", sa.JSON()))
    op.alter_column(
        "companies",
        "logo_path",
        new_column_name="reference_design_path",
    )
    op.alter_column("companies", "name", new_column_name="company")
    op.alter_column("companies", "id", new_column_name="company_id")
    op.drop_column("companies", "posts_per_week")
    op.drop_column("companies", "audiences")
    op.drop_column("companies", "tone")
    op.drop_column("companies", "secondary_color")
    op.drop_column("companies", "primary_color")
    op.drop_column("companies", "language")
    tone_enum.drop(op.get_bind(), checkfirst=True)
    language_enum.drop(op.get_bind(), checkfirst=True)
    op.rename_table("companies", "company_model")
