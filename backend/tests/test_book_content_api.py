import json
import uuid

import pytest
from fastapi import HTTPException

from app.api.routes.books import (
    _build_book_content_response,
    _load_references_index,
    _read_reference_chapter,
    _references_dir,
)
from app.models.models import Book


def make_book(book_id: uuid.UUID, status: str = "ready") -> Book:
    return Book(
        id=book_id,
        title="Book",
        author="Author",
        file_path="/tmp/book.epub",
        file_type="epub",
        status=status,
    )


def write_refs(root, book_id):
    ref_dir = root / str(book_id) / "references"
    ref_dir.mkdir(parents=True)
    index = {
        "book_title": "Book",
        "total_chapters": 2,
        "chapters": [
            {
                "chapter_num": 1,
                "title": "One",
                "page_start": 1,
                "page_end": 5,
                "file": "ch01_One.md",
                "summary_file": "ch01_One_summary.md",
                "char_count": 11,
            },
            {
                "chapter_num": 2,
                "title": "Two",
                "page_start": 6,
                "page_end": 9,
                "file": "ch02_Two.md",
                "summary_file": "ch02_Two_summary.md",
                "char_count": 12,
            },
        ],
    }
    (ref_dir / "index.json").write_text(json.dumps(index), encoding="utf-8")
    (ref_dir / "ch01_One.md").write_text("# One\n\nfull one", encoding="utf-8")
    (ref_dir / "ch02_Two.md").write_text("# Two\n\nfull two", encoding="utf-8")
    (ref_dir / "ch01_One_summary.md").write_text("summary", encoding="utf-8")
    return ref_dir


def test_references_dir_uses_storage_root(tmp_path, monkeypatch):
    monkeypatch.setattr("app.api.routes.books.settings.STORAGE_LOCAL_PATH", str(tmp_path))
    book_id = uuid.uuid4()

    assert _references_dir(book_id) == tmp_path / str(book_id) / "references"


def test_load_references_index_reads_index(tmp_path):
    book_id = uuid.uuid4()
    ref_dir = write_refs(tmp_path, book_id)

    index = _load_references_index(ref_dir)

    assert index["book_title"] == "Book"
    assert len(index["chapters"]) == 2


def test_load_references_index_raises_for_missing_index(tmp_path):
    with pytest.raises(HTTPException) as exc:
        _load_references_index(tmp_path)

    assert exc.value.status_code == 404


def test_read_reference_chapter_reads_full_chapter(tmp_path):
    book_id = uuid.uuid4()
    ref_dir = write_refs(tmp_path, book_id)
    index = _load_references_index(ref_dir)

    content = _read_reference_chapter(ref_dir, index["chapters"][0])

    assert "full one" in content


def test_build_book_content_response_index_mode_has_no_bodies(tmp_path):
    book_id = uuid.uuid4()
    book = make_book(book_id)
    ref_dir = write_refs(tmp_path, book_id)

    response = _build_book_content_response(book, ref_dir, mode="index", chapter_num=None)

    assert response.mode == "index"
    assert response.chapters[0].content is None


def test_build_book_content_response_chapter_mode_requires_chapter_num(tmp_path):
    book_id = uuid.uuid4()
    book = make_book(book_id)
    ref_dir = write_refs(tmp_path, book_id)

    with pytest.raises(HTTPException) as exc:
        _build_book_content_response(book, ref_dir, mode="chapter", chapter_num=None)

    assert exc.value.status_code == 400


def test_build_book_content_response_full_mode_includes_all_bodies(tmp_path):
    book_id = uuid.uuid4()
    book = make_book(book_id)
    ref_dir = write_refs(tmp_path, book_id)

    response = _build_book_content_response(book, ref_dir, mode="full", chapter_num=None)

    assert [chapter.content for chapter in response.chapters] == ["# One\n\nfull one", "# Two\n\nfull two"]
