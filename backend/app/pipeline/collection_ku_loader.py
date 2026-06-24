import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Book, BookKnowledgeUnit, Collection, CollectionBook
from app.pipeline.book_knowledge_unit_store import (
    book_ku_to_knowledge_unit,
    load_book_knowledge_unit_rows,
)
from app.schemas.schemas import KnowledgeUnit


class MissingReusableKUsError(ValueError):
    pass


def annotate_book_table_ku_rows(book: Book, rows: list[BookKnowledgeUnit]) -> list[KnowledgeUnit]:
    annotated: list[KnowledgeUnit] = []
    for row in rows:
        ku = book_ku_to_knowledge_unit(row)
        payload = ku.model_dump()
        source_ref = {
            "book_id": str(book.id),
            "title": book.title,
            "author": book.author,
            "chapter_num": ku.source_chapter_num,
            "chunk_id": ku.source_chunk_id,
            "skill_package_id": str(row.skill_package_id) if row.skill_package_id else None,
        }
        payload["source_book_id"] = str(book.id)
        payload["source_book_title"] = book.title
        payload["source_book_author"] = book.author
        payload["source_books"] = [source_ref]
        annotated.append(KnowledgeUnit(**payload))
    return annotated


async def load_collection_with_books(
    db: AsyncSession,
    collection_id: uuid.UUID,
) -> Collection:
    result = await db.execute(
        select(Collection)
        .where(Collection.id == collection_id)
        .options(selectinload(Collection.books).selectinload(CollectionBook.book))
    )
    collection = result.scalar_one_or_none()
    if not collection:
        raise ValueError("书单不存在")
    return collection


async def load_book_kus(
    db: AsyncSession,
    book: Book,
) -> list[KnowledgeUnit]:
    rows = await load_book_knowledge_unit_rows(db, book.id)
    if not rows:
        raise MissingReusableKUsError(
            f"《{book.title or book.id}》没有可复用 KU，请先提交或生成该书的 knowledge units"
        )
    return annotate_book_table_ku_rows(book, rows)
