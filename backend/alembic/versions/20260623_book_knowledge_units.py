"""add book knowledge units

Revision ID: 20260623_book_knowledge_units
Revises: 20260618_collection_skill_pkgs
Create Date: 2026-06-23 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260623_book_knowledge_units"
down_revision: Union[str, None] = "20260618_collection_skill_pkgs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "book_knowledge_units",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_package_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_chunk_id", sa.Text(), nullable=True),
        sa.Column("source_chapter_num", sa.Integer(), nullable=False),
        sa.Column("source_quote", sa.Text(), nullable=True),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("generated_by", sa.String(length=50), nullable=False),
        sa.Column("generator_name", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_package_id"], ["skill_packages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_book_knowledge_units_book_id"),
        "book_knowledge_units",
        ["book_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_book_knowledge_units_skill_package_id"),
        "book_knowledge_units",
        ["skill_package_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_book_knowledge_units_skill_package_id"),
        table_name="book_knowledge_units",
    )
    op.drop_index(op.f("ix_book_knowledge_units_book_id"), table_name="book_knowledge_units")
    op.drop_table("book_knowledge_units")
