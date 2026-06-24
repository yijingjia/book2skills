import uuid

from app.models.models import Book, BookKnowledgeUnit
from app.pipeline.collection_ku_loader import annotate_book_table_ku_rows


def test_annotate_book_table_ku_rows_adds_source_books_metadata():
    book = Book(
        id=uuid.uuid4(),
        title="底层逻辑",
        author="刘润",
        file_path="x",
        file_type="pdf",
    )
    package_id = uuid.uuid4()
    rows = [
        BookKnowledgeUnit(
            id=uuid.uuid4(),
            book_id=book.id,
            skill_package_id=package_id,
            source_chunk_id="book_ch1_0",
            source_chapter_num=1,
            source_quote="系统由要素、关系和目标构成。",
            content={
                "principle": "系统要看关系和目标。",
                "method": "系统思维",
                "step_by_step": ["看要素", "看关系"],
                "example": None,
                "when_to_use": ["复杂问题"],
            },
            tags=[],
            generated_by="agent",
            generator_name="codex",
        )
    ]

    annotated = annotate_book_table_ku_rows(book, rows)

    assert annotated[0].source_book_id == str(book.id)
    assert annotated[0].method == "系统思维"
    assert annotated[0].source_books[0]["chapter_num"] == 1
    assert annotated[0].source_books[0]["chunk_id"] == "book_ch1_0"
    assert annotated[0].source_books[0]["skill_package_id"] == str(package_id)
