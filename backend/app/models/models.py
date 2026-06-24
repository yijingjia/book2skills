import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Book(Base):
    __tablename__ = "books"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(String(1000))
    file_type: Mapped[str] = mapped_column(String(10))  # 'pdf' | 'epub'
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    # 'pending' | 'processing' | 'ready' | 'error'
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    chapters: Mapped[list["Chapter"]] = relationship("Chapter", back_populates="book", cascade="all, delete-orphan")
    skill_packages: Mapped[list["SkillPackage"]] = relationship("SkillPackage", back_populates="book", cascade="all, delete-orphan")
    knowledge_units: Mapped[list["BookKnowledgeUnit"]] = relationship(
        "BookKnowledgeUnit",
        back_populates="book",
        cascade="all, delete-orphan",
    )
    collection_memberships: Mapped[list["CollectionBook"]] = relationship(
        "CollectionBook",
        back_populates="book",
        cascade="all, delete-orphan",
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("books.id"))
    title: Mapped[str] = mapped_column(String(500))
    chapter_num: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)

    book: Mapped["Book"] = relationship("Book", back_populates="chapters")


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    books: Mapped[list["CollectionBook"]] = relationship(
        "CollectionBook",
        back_populates="collection",
        cascade="all, delete-orphan",
        order_by="CollectionBook.order_index",
    )
    skill_packages: Mapped[list["CollectionSkillPackage"]] = relationship(
        "CollectionSkillPackage",
        back_populates="collection",
        cascade="all, delete-orphan",
    )


class CollectionBook(Base):
    __tablename__ = "collection_books"
    __table_args__ = (
        UniqueConstraint("collection_id", "book_id", name="uq_collection_books_collection_book"),
        UniqueConstraint("collection_id", "order_index", name="uq_collection_books_collection_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        index=True,
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("books.id", ondelete="CASCADE"),
        index=True,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    collection: Mapped["Collection"] = relationship("Collection", back_populates="books")
    book: Mapped["Book"] = relationship("Book", back_populates="collection_memberships")


class CollectionSkillPackage(Base):
    __tablename__ = "collection_skill_packages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skill_md: Mapped[str | None] = mapped_column(Text)
    scripts: Mapped[dict | None] = mapped_column(JSONB)
    templates: Mapped[dict | None] = mapped_column(JSONB)
    zip_path: Mapped[str | None] = mapped_column(String(1000))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    collection: Mapped["Collection"] = relationship("Collection", back_populates="skill_packages")


class SkillPackage(Base):
    __tablename__ = "skill_packages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("books.id"))
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skill_md: Mapped[str | None] = mapped_column(Text)
    scripts: Mapped[dict | None] = mapped_column(JSONB)
    templates: Mapped[dict | None] = mapped_column(JSONB)
    zip_path: Mapped[str | None] = mapped_column(String(1000))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    # 'draft' | 'generating' | 'ready' | 'error'
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    book: Mapped["Book"] = relationship("Book", back_populates="skill_packages")
    conversations: Mapped[list["Conversation"]] = relationship("Conversation", back_populates="skill_package", cascade="all, delete-orphan")
    skills: Mapped[list["Skill"]] = relationship("Skill", back_populates="skill_package", cascade="all, delete-orphan")


class BookKnowledgeUnit(Base):
    __tablename__ = "book_knowledge_units"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("books.id", ondelete="CASCADE"),
        index=True,
    )
    skill_package_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skill_packages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_chunk_id: Mapped[str | None] = mapped_column(Text)
    source_chapter_num: Mapped[int] = mapped_column(Integer)
    source_quote: Mapped[str | None] = mapped_column(Text)
    content: Mapped[dict] = mapped_column(JSONB)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    generated_by: Mapped[str] = mapped_column(String(50))
    generator_name: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    book: Mapped["Book"] = relationship("Book", back_populates="knowledge_units")
    skill_package: Mapped["SkillPackage"] = relationship("SkillPackage")


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("books.id"))
    skill_package_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("skill_packages.id"), nullable=True)

    name: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    when_to_use: Mapped[dict | list | None] = mapped_column(JSONB)
    workflow: Mapped[dict | list | None] = mapped_column(JSONB)
    templates: Mapped[dict | list | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    book: Mapped["Book"] = relationship("Book")
    skill_package: Mapped["SkillPackage"] = relationship("SkillPackage", back_populates="skills")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    skill_package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("skill_packages.id"))
    role: Mapped[str] = mapped_column(String(20))  # 'user' | 'assistant'
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    skill_package: Mapped["SkillPackage"] = relationship("SkillPackage", back_populates="conversations")
