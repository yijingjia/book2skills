import json
import uuid

import pytest

from app.models.models import Book, SkillPackage
from app.pipeline.collection_ku_loader import (
    MissingReusableKUsError,
    annotate_source_kus,
    extract_kus_from_scripts,
)
from app.schemas.schemas import KnowledgeUnit


def make_book(title: str = "产品书") -> Book:
    return Book(
        id=uuid.uuid4(),
        title=title,
        author="Author",
        file_path=f"/tmp/{title}.epub",
        file_type="epub",
        status="ready",
    )


def test_extract_kus_from_scripts_prefers_complete_json():
    ku = KnowledgeUnit(source_chunk_id="c1", source_chapter_num=1, principle="验证需求")
    scripts = {
        "extracted_kus_partial.json": "[]",
        "extracted_kus.json": json.dumps([ku.model_dump()], ensure_ascii=False),
    }

    result = extract_kus_from_scripts(scripts)

    assert len(result) == 1
    assert result[0].principle == "验证需求"


def test_extract_kus_from_scripts_raises_when_missing():
    with pytest.raises(MissingReusableKUsError):
        extract_kus_from_scripts({"other.json": "[]"})


def test_annotate_source_kus_adds_book_metadata():
    book = make_book("产品书 A")
    package = SkillPackage(book_id=book.id, scripts={})
    ku = KnowledgeUnit(source_chunk_id="c1", source_chapter_num=3, principle="先访谈")

    result = annotate_source_kus(book, package, [ku])

    assert result[0].source_book_id == str(book.id)
    assert result[0].source_book_title == "产品书 A"
    assert result[0].source_books[0]["chapter_num"] == 3
