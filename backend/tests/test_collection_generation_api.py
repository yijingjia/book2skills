import uuid
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.api.routes.collections import _ensure_collection_generateable
from app.models.models import Book, Collection, CollectionBook


def book(status: str = "ready") -> Book:
    return Book(id=uuid.uuid4(), title="Book", file_path="/tmp/a.epub", file_type="epub", status=status)


def collection_with_books(books: list[Book]) -> Collection:
    collection = Collection(id=uuid.uuid4(), name="合集", status="active", created_at=datetime(2026, 6, 18), updated_at=datetime(2026, 6, 18))
    collection.books = [CollectionBook(book=b, book_id=b.id, order_index=i) for i, b in enumerate(books)]
    return collection


def test_ensure_collection_generateable_requires_two_books():
    with pytest.raises(HTTPException) as exc:
        _ensure_collection_generateable(collection_with_books([book()]))

    assert exc.value.status_code == 400
    assert "至少两本书" in exc.value.detail


def test_ensure_collection_generateable_rejects_non_ready_book():
    with pytest.raises(HTTPException) as exc:
        _ensure_collection_generateable(collection_with_books([book(), book(status="processing")]))

    assert exc.value.status_code == 400
    assert "尚未处理完成" in exc.value.detail
