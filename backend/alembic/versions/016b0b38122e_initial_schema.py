"""initial_schema

Revision ID: 016b0b38122e
Revises:
Create Date: 2026-03-17 02:27:51.205402

NOTE: autogenerate generated an empty migration because the tables already
exist in the database (they were created by create_all() at startup).
This migration represents the canonical initial schema so future migrations
have a proper base. When running on a fresh database, execute:
    alembic upgrade head
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '016b0b38122e'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all tables from scratch (initial schema)."""
    # --- books ---
    op.create_table(
        'books',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.String(length=100), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=True),
        sa.Column('author', sa.String(length=500), nullable=True),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('file_type', sa.String(length=10), nullable=False),
        sa.Column('page_count', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_books_file_hash'), 'books', ['file_hash'], unique=False)

    # --- chapters ---
    op.create_table(
        'chapters',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('book_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('chapter_num', sa.Integer(), nullable=False),
        sa.Column('page_start', sa.Integer(), nullable=True),
        sa.Column('page_end', sa.Integer(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['book_id'], ['books.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # --- skill_packages ---
    op.create_table(
        'skill_packages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('book_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.String(length=100), nullable=True),
        sa.Column('skill_md', sa.Text(), nullable=True),
        sa.Column('scripts', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('templates', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('zip_path', sa.String(length=1000), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['books.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # --- skills ---
    op.create_table(
        'skills',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('book_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('skill_package_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('name', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('when_to_use', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('workflow', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('templates', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['books.id']),
        sa.ForeignKeyConstraint(['skill_package_id'], ['skill_packages.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # --- conversations ---
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('skill_package_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['skill_package_id'], ['skill_packages.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.drop_table('conversations')
    op.drop_table('skills')
    op.drop_table('skill_packages')
    op.drop_table('chapters')
    op.drop_index(op.f('ix_books_file_hash'), table_name='books')
    op.drop_table('books')
