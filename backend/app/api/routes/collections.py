"""API 路由 — Collection 书单管理"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.models import Book, Collection, CollectionBook
from app.schemas.schemas import (
    CollectionBookSummary,
    CollectionCreateRequest,
    CollectionDetailResponse,
    CollectionListResponse,
    CollectionUpdateRequest,
)

router = APIRouter(prefix="/api/collections", tags=["collections"])


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
