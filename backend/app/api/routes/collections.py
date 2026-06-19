"""API 路由 — Collection 书单管理"""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.models import Book, Collection, CollectionBook, CollectionSkillPackage
from app.schemas.schemas import (
    CollectionBookSummary,
    CollectionCreateRequest,
    CollectionDetailResponse,
    CollectionListResponse,
    CollectionSkillPackageListItem,
    CollectionSkillPackageResponse,
    CollectionUpdateRequest,
    GenerateCollectionSkillRequest,
)
from app.tasks.generate_collection_skill import generate_collection_skill_task

router = APIRouter(prefix="/api/collections", tags=["collections"])
STALE_GENERATING_AFTER = timedelta(minutes=30)


def _validate_ready_books(book_ids: list[uuid.UUID], books: list[Book]) -> list[Book]:
    books_by_id = {book.id: book for book in books}
    ordered_books = []

    for book_id in book_ids:
        book = books_by_id.get(book_id)
        if not book:
            raise HTTPException(404, detail=f"书籍不存在：{book_id}")
        if book.status != "ready":
            title = book.title or str(book.id)
            raise HTTPException(400, detail=f"书籍尚未处理完成：{title} 当前状态：{book.status}")
        ordered_books.append(book)

    return ordered_books


def _build_collection_list_response(collection: Collection) -> CollectionListResponse:
    return CollectionListResponse(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        status=collection.status,
        book_count=len(collection.books or []),
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


def _build_collection_detail_response(collection: Collection) -> CollectionDetailResponse:
    ordered_memberships = sorted(collection.books or [], key=lambda item: item.order_index)
    books = [
        CollectionBookSummary(
            book_id=membership.book.id,
            title=membership.book.title,
            author=membership.book.author,
            status=membership.book.status,
            page_count=membership.book.page_count,
            order_index=membership.order_index,
        )
        for membership in ordered_memberships
        if membership.book is not None
    ]
    return CollectionDetailResponse(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        status=collection.status,
        books=books,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


def _is_retryable_collection_skill(package: CollectionSkillPackage) -> bool:
    if package.status == "error":
        return True
    if package.status != "generating":
        return False
    created_at = package.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - created_at > STALE_GENERATING_AFTER


def _build_collection_skill_list_item(
    package: CollectionSkillPackage,
) -> CollectionSkillPackageListItem:
    scripts = package.scripts or {}
    return CollectionSkillPackageListItem(
        id=package.id,
        collection_id=package.collection_id,
        status=package.status,
        zip_path=package.zip_path,
        version=package.version,
        pipeline_phase=scripts.get("pipeline_phase"),
        failed_reason=scripts.get("failed_reason"),
        is_retryable=_is_retryable_collection_skill(package),
        created_at=package.created_at,
        updated_at=package.updated_at,
    )


async def _load_books_by_ids(db: AsyncSession, book_ids: list[uuid.UUID]) -> list[Book]:
    result = await db.execute(select(Book).where(Book.id.in_(book_ids)))
    return list(result.scalars().all())


async def _get_collection_or_404(
    collection_id: uuid.UUID,
    db: AsyncSession,
) -> Collection:
    result = await db.execute(
        select(Collection)
        .where(Collection.id == collection_id)
        .options(selectinload(Collection.books).selectinload(CollectionBook.book))
    )
    collection = result.scalar_one_or_none()
    if not collection:
        raise HTTPException(404, detail="书单不存在")
    return collection


def _build_collection_book_memberships(
    collection_id: uuid.UUID,
    books: list[Book],
) -> list[CollectionBook]:
    return [
        CollectionBook(
            collection_id=collection_id,
            book_id=book.id,
            book=book,
            order_index=index,
        )
        for index, book in enumerate(books)
    ]


@router.get("", response_model=list[CollectionListResponse])
async def list_collections(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Collection)
        .options(selectinload(Collection.books))
        .order_by(desc(Collection.created_at))
    )
    collections = result.scalars().all()
    return [_build_collection_list_response(collection) for collection in collections]


@router.post("", response_model=CollectionDetailResponse)
async def create_collection(
    request: CollectionCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    books = _validate_ready_books(request.book_ids, await _load_books_by_ids(db, request.book_ids))
    collection = Collection(
        name=request.name,
        description=request.description,
        status="active",
    )
    db.add(collection)
    await db.flush()
    db.add_all(_build_collection_book_memberships(collection.id, books))
    await db.commit()

    created = await _get_collection_or_404(collection.id, db)
    return _build_collection_detail_response(created)


def _ensure_collection_generateable(collection: Collection) -> None:
    memberships = collection.books or []
    if len(memberships) < 2:
        raise HTTPException(400, detail="综合 skill 至少两本书才能生成")
    for membership in memberships:
        if membership.book is None:
            raise HTTPException(400, detail="书单包含无法读取的书籍")
        if membership.book.status != "ready":
            title = membership.book.title or str(membership.book_id)
            raise HTTPException(400, detail=f"书籍尚未处理完成：{title} 当前状态：{membership.book.status}")


@router.post("/{collection_id}/generate", response_model=CollectionSkillPackageResponse)
async def generate_collection_skill(
    collection_id: uuid.UUID,
    request: GenerateCollectionSkillRequest,
    db: AsyncSession = Depends(get_db),
):
    if not request.reuse_extracted_kus:
        raise HTTPException(400, detail="当前版本只支持复用已提取 KU，请先保持 reuse_extracted_kus=true")

    collection = await _get_collection_or_404(collection_id, db)
    _ensure_collection_generateable(collection)

    package = CollectionSkillPackage(
        collection_id=collection_id,
        status="generating",
    )
    db.add(package)
    await db.commit()
    await db.refresh(package)

    generate_collection_skill_task.delay(
        skill_package_id=str(package.id),
        collection_id=str(collection_id),
        user_goal=request.user_goal,
        detect_conflicts=request.detect_conflicts,
    )

    return CollectionSkillPackageResponse.model_validate(package)


@router.get("/{collection_id}/skills", response_model=list[CollectionSkillPackageListItem])
async def list_collection_skills(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await _get_collection_or_404(collection_id, db)
    result = await db.execute(
        select(CollectionSkillPackage)
        .where(CollectionSkillPackage.collection_id == collection_id)
        .order_by(CollectionSkillPackage.created_at.desc())
    )
    packages = list(result.scalars().all())
    return [_build_collection_skill_list_item(package) for package in packages]


@router.get("/{collection_id}", response_model=CollectionDetailResponse)
async def get_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    collection = await _get_collection_or_404(collection_id, db)
    return _build_collection_detail_response(collection)


@router.patch("/{collection_id}", response_model=CollectionDetailResponse)
async def update_collection(
    collection_id: uuid.UUID,
    request: CollectionUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    collection = await _get_collection_or_404(collection_id, db)

    if request.name is not None:
        collection.name = request.name
    if request.description is not None:
        collection.description = request.description
    if request.book_ids is not None:
        books = _validate_ready_books(
            request.book_ids,
            await _load_books_by_ids(db, request.book_ids),
        )
        collection.books.clear()
        await db.flush()
        db.add_all(_build_collection_book_memberships(collection.id, books))

    await db.commit()
    updated = await _get_collection_or_404(collection_id, db)
    return _build_collection_detail_response(updated)


@router.delete("/{collection_id}")
async def delete_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    collection = await _get_collection_or_404(collection_id, db)
    await db.delete(collection)
    await db.commit()
    return {"message": "collection deleted"}
