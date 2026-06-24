import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.sql.dml import Delete

from app.api.routes.books import (
    _book_graph_delete_statements,
    _ensure_book_deletable,
    _find_invalidated_collection_ids,
    _local_book_storage_dir,
    _safe_delete_path,
)
from app.models.models import Book


def make_book(status: str = "ready") -> Book:
    return Book(
        id=uuid.uuid4(),
        title="Book",
        author="Author",
        file_path="/tmp/book.pdf",
        file_type="pdf",
        status=status,
    )


def test_ensure_book_deletable_rejects_active_processing_statuses():
    for status in ("pending", "processing"):
        with pytest.raises(HTTPException) as exc:
            _ensure_book_deletable(make_book(status))
        assert exc.value.status_code == 409


def test_ensure_book_deletable_allows_ready_and_error():
    _ensure_book_deletable(make_book("ready"))
    _ensure_book_deletable(make_book("error"))


def test_local_book_storage_dir_uses_storage_root(tmp_path, monkeypatch):
    monkeypatch.setattr("app.api.routes.books.settings.STORAGE_LOCAL_PATH", str(tmp_path))
    book_id = uuid.uuid4()

    assert _local_book_storage_dir(book_id) == tmp_path / str(book_id)


def test_safe_delete_path_removes_directory(tmp_path):
    target = tmp_path / "book-storage"
    target.mkdir()
    (target / "file.txt").write_text("data", encoding="utf-8")

    _safe_delete_path(target)

    assert not target.exists()


def test_safe_delete_path_ignores_missing_path(tmp_path):
    _safe_delete_path(tmp_path / "missing")


def test_find_invalidated_collection_ids_returns_collections_that_fall_below_two_books():
    book_id = uuid.uuid4()
    keep_collection = uuid.uuid4()
    delete_collection = uuid.uuid4()
    rows = [
        {"collection_id": keep_collection, "book_id": book_id},
        {"collection_id": keep_collection, "book_id": uuid.uuid4()},
        {"collection_id": keep_collection, "book_id": uuid.uuid4()},
        {"collection_id": delete_collection, "book_id": book_id},
        {"collection_id": delete_collection, "book_id": uuid.uuid4()},
    ]

    assert _find_invalidated_collection_ids(book_id, rows) == {delete_collection}


def test_book_graph_delete_statements_are_explicit_and_ordered():
    book_id = uuid.uuid4()
    invalidated_collection_ids = {uuid.uuid4(), uuid.uuid4()}

    statements = _book_graph_delete_statements(book_id, invalidated_collection_ids)

    assert all(isinstance(statement, Delete) for statement in statements)
    assert [statement.table.name for statement in statements] == [
        "conversations",
        "skills",
        "skill_packages",
        "chapters",
        "collection_skill_packages",
        "collection_books",
        "collections",
        "books",
    ]
