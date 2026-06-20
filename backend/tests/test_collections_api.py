import uuid
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.api.routes.collections import (
    _build_collection_book_memberships,
    _build_collection_detail_response,
    _build_collection_list_response,
    _local_collection_storage_dir,
    _safe_delete_collection_storage,
    _validate_ready_books,
)
from app.models.models import Book, Collection, CollectionBook


def make_book(book_id: uuid.UUID, status: str = "ready", title: str = "Book") -> Book:
    return Book(
        id=book_id,
        title=title,
        author="Author",
        file_path=f"/tmp/{book_id}.epub",
        file_type="epub",
        page_count=100,
        status=status,
    )


def test_validate_ready_books_rejects_missing_book():
    book_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc:
        _validate_ready_books([book_id], [])

    assert exc.value.status_code == 404
    assert "书籍不存在" in exc.value.detail


def test_validate_ready_books_rejects_non_ready_book():
    book_id = uuid.uuid4()
    book = make_book(book_id, status="processing")

    with pytest.raises(HTTPException) as exc:
        _validate_ready_books([book_id], [book])

    assert exc.value.status_code == 400
    assert "尚未处理完成" in exc.value.detail


def test_validate_ready_books_preserves_request_order():
    first = uuid.uuid4()
    second = uuid.uuid4()
    books = [
        make_book(second, title="Second"),
        make_book(first, title="First"),
    ]

    ordered = _validate_ready_books([first, second], books)

    assert [book.id for book in ordered] == [first, second]


def test_build_collection_detail_response_orders_books():
    collection_id = uuid.uuid4()
    first = make_book(uuid.uuid4(), title="First")
    second = make_book(uuid.uuid4(), title="Second")
    collection = Collection(
        id=collection_id,
        name="产品方法论",
        description="desc",
        status="active",
        created_at=datetime(2026, 6, 18),
        updated_at=datetime(2026, 6, 18),
    )
    collection.books = [
        CollectionBook(book=second, book_id=second.id, order_index=1),
        CollectionBook(book=first, book_id=first.id, order_index=0),
    ]

    response = _build_collection_detail_response(collection)

    assert response.id == collection_id
    assert response.name == "产品方法论"
    assert [book.title for book in response.books] == ["First", "Second"]
    assert [book.order_index for book in response.books] == [0, 1]


def test_build_collection_list_response_counts_books():
    collection = Collection(
        id=uuid.uuid4(),
        name="产品方法论",
        status="active",
        created_at=datetime(2026, 6, 18),
        updated_at=datetime(2026, 6, 18),
    )
    collection.books = [
        CollectionBook(book_id=uuid.uuid4(), order_index=0),
        CollectionBook(book_id=uuid.uuid4(), order_index=1),
    ]

    response = _build_collection_list_response(collection)

    assert response.book_count == 2
    assert response.status == "active"


def test_build_collection_book_memberships_preserves_order():
    collection_id = uuid.uuid4()
    first = make_book(uuid.uuid4(), title="First")
    second = make_book(uuid.uuid4(), title="Second")

    memberships = _build_collection_book_memberships(collection_id, [first, second])

    assert [membership.collection_id for membership in memberships] == [collection_id, collection_id]
    assert [membership.book_id for membership in memberships] == [first.id, second.id]
    assert [membership.order_index for membership in memberships] == [0, 1]


def test_local_collection_storage_dir_uses_storage_root(tmp_path, monkeypatch):
    monkeypatch.setattr("app.api.routes.collections.settings.STORAGE_LOCAL_PATH", str(tmp_path))
    collection_id = uuid.uuid4()

    assert _local_collection_storage_dir(collection_id) == tmp_path / "collections" / str(collection_id)


def test_safe_delete_collection_storage_removes_directory(tmp_path):
    target = tmp_path / "collections" / "abc"
    target.mkdir(parents=True)
    (target / "skills.zip").write_text("zip", encoding="utf-8")

    _safe_delete_collection_storage(target)

    assert not target.exists()
