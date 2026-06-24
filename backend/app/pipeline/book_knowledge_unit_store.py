import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Book, BookKnowledgeUnit
from app.schemas.schemas import KnowledgeUnit


def knowledge_unit_to_content(ku: KnowledgeUnit) -> dict[str, Any]:
    return {
        "principle": ku.principle,
        "method": ku.method,
        "step_by_step": ku.step_by_step,
        "example": ku.example,
        "when_to_use": ku.when_to_use,
    }


def book_ku_to_knowledge_unit(row: BookKnowledgeUnit) -> KnowledgeUnit:
    content = dict(row.content or {})
    return KnowledgeUnit(
        source_chunk_id=row.source_chunk_id or f"{row.book_id}_ch{row.source_chapter_num}_ku_{row.id}",
        source_chapter_num=row.source_chapter_num,
        principle=content.get("principle"),
        method=content.get("method"),
        step_by_step=content.get("step_by_step") or [],
        example=content.get("example"),
        when_to_use=content.get("when_to_use") or [],
    )


def build_book_ku_row(
    *,
    book_id: uuid.UUID,
    ku: KnowledgeUnit,
    source_quote: str | None,
    generated_by: str,
    generator_name: str | None,
    skill_package_id: uuid.UUID | None,
    tags: list[str] | None = None,
) -> BookKnowledgeUnit:
    return BookKnowledgeUnit(
        book_id=book_id,
        skill_package_id=skill_package_id,
        source_chunk_id=ku.source_chunk_id,
        source_chapter_num=ku.source_chapter_num,
        source_quote=source_quote,
        content=knowledge_unit_to_content(ku),
        tags=tags or [],
        generated_by=generated_by,
        generator_name=generator_name,
    )


async def replace_book_knowledge_units(
    *,
    db: AsyncSession,
    book_id: uuid.UUID,
    units: list[dict[str, Any]],
    generated_by: str,
    generator_name: str | None,
    skill_package_id: uuid.UUID | None,
) -> list[BookKnowledgeUnit]:
    await db.execute(delete(BookKnowledgeUnit).where(BookKnowledgeUnit.book_id == book_id))
    rows = [
        build_book_ku_row(
            book_id=book_id,
            ku=item["ku"],
            source_quote=item["source_quote"],
            generated_by=generated_by,
            generator_name=generator_name,
            skill_package_id=skill_package_id,
            tags=item.get("tags") or [],
        )
        for item in units
    ]
    db.add_all(rows)
    await db.flush()
    return rows


async def book_has_knowledge_units(db: AsyncSession, book_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(BookKnowledgeUnit.id).where(BookKnowledgeUnit.book_id == book_id).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def load_book_knowledge_units(db: AsyncSession, book: Book) -> list[KnowledgeUnit]:
    return await load_book_knowledge_units_for_book_id(db, book.id)


async def load_book_knowledge_units_for_book_id(
    db: AsyncSession,
    book_id: uuid.UUID,
) -> list[KnowledgeUnit]:
    rows = await load_book_knowledge_unit_rows(db, book_id)
    return [book_ku_to_knowledge_unit(row) for row in rows]


async def load_book_knowledge_unit_rows(
    db: AsyncSession,
    book_id: uuid.UUID,
) -> list[BookKnowledgeUnit]:
    result = await db.execute(
        select(BookKnowledgeUnit)
        .where(BookKnowledgeUnit.book_id == book_id)
        .order_by(BookKnowledgeUnit.source_chapter_num, BookKnowledgeUnit.created_at)
    )
    return list(result.scalars().all())
