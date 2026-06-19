import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Book, Collection, CollectionBook, SkillPackage
from app.schemas.schemas import KnowledgeUnit


class MissingReusableKUsError(ValueError):
    pass


def extract_kus_from_scripts(scripts: dict | None) -> list[KnowledgeUnit]:
    if not scripts:
        raise MissingReusableKUsError("未找到可复用的 KU：技能包 scripts 为空")
    raw = scripts.get("extracted_kus.json") or scripts.get("extracted_kus_partial.json")
    if not raw:
        raise MissingReusableKUsError("未找到 extracted_kus.json 或 extracted_kus_partial.json")
    data = json.loads(raw)
    return [KnowledgeUnit(**item) for item in data]


def annotate_source_kus(
    book: Book,
    package: SkillPackage,
    kus: list[KnowledgeUnit],
) -> list[KnowledgeUnit]:
    annotated: list[KnowledgeUnit] = []
    for ku in kus:
        payload = ku.model_dump()
        source_ref = {
            "book_id": str(book.id),
            "title": book.title,
            "author": book.author,
            "chapter_num": ku.source_chapter_num,
            "chunk_id": ku.source_chunk_id,
            "skill_package_id": str(package.id) if package.id else None,
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


async def load_latest_book_kus(
    db: AsyncSession,
    book: Book,
) -> list[KnowledgeUnit]:
    stmt = (
        select(SkillPackage)
        .where(SkillPackage.book_id == book.id)
        .where(SkillPackage.scripts.isnot(None))
        .order_by(SkillPackage.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    package = result.scalar_one_or_none()
    if not package:
        raise MissingReusableKUsError(f"《{book.title or book.id}》没有可复用 KU，请先生成单书 skill")
    kus = extract_kus_from_scripts(package.scripts)
    if not kus:
        raise MissingReusableKUsError(f"《{book.title or book.id}》没有可复用 KU")
    return annotate_source_kus(book, package, kus)
