"""add collection skill packages

Revision ID: 20260618_collection_skill_pkgs
Revises: 20260618_add_collections
Create Date: 2026-06-18 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260618_collection_skill_pkgs"
down_revision: Union[str, None] = "20260618_add_collections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "collection_skill_packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=True),
        sa.Column("skill_md", sa.Text(), nullable=True),
        sa.Column("scripts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("templates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("zip_path", sa.String(length=1000), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_collection_skill_packages_collection_id"),
        "collection_skill_packages",
        ["collection_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_collection_skill_packages_collection_id"),
        table_name="collection_skill_packages",
    )
    op.drop_table("collection_skill_packages")
