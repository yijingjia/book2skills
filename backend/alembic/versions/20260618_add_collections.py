"""add collections

Revision ID: 20260618_add_collections
Revises: 016b0b38122e
Create Date: 2026-06-18 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260618_add_collections"
down_revision: Union[str, None] = "016b0b38122e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "collection_books",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_id",
            "book_id",
            name="uq_collection_books_collection_book",
        ),
        sa.UniqueConstraint(
            "collection_id",
            "order_index",
            name="uq_collection_books_collection_order",
        ),
    )
    op.create_index(
        op.f("ix_collection_books_book_id"),
        "collection_books",
        ["book_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collection_books_collection_id"),
        "collection_books",
        ["collection_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_collection_books_collection_id"), table_name="collection_books")
    op.drop_index(op.f("ix_collection_books_book_id"), table_name="collection_books")
    op.drop_table("collection_books")
    op.drop_table("collections")
