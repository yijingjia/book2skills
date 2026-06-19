import numpy as np

from app.pipeline.collection_ku_processor import merge_source_preserving_similar_kus
from app.schemas.schemas import KnowledgeUnit


def make_ku(book_id: str, title: str, principle: str, method: str = "MVP") -> KnowledgeUnit:
    return KnowledgeUnit(
        source_chunk_id=f"{book_id}-chunk",
        source_chapter_num=1,
        principle=principle,
        method=method,
        source_book_id=book_id,
        source_book_title=title,
        source_books=[
            {
                "book_id": book_id,
                "title": title,
                "author": None,
                "chapter_num": 1,
                "chunk_id": f"{book_id}-chunk",
            }
        ],
    )


def test_merge_source_preserving_similar_kus_preserves_sources():
    first = make_ku("book-1", "精益创业", "先用 MVP 验证需求")
    second = make_ku("book-2", "产品验证", "通过最小可行产品先验证需求")
    embeddings = np.array([
        [1.0, 0.0, 0.0],
        [0.96, 0.04, 0.0],
    ])

    merged = merge_source_preserving_similar_kus([first, second], embeddings, threshold=0.9)

    assert len(merged) == 1
    assert len(merged[0].source_books) == 2
    assert {source["book_id"] for source in merged[0].source_books} == {"book-1", "book-2"}


def test_merge_source_preserving_similar_kus_keeps_distinct_embeddings():
    first = make_ku("book-1", "A", "先访谈用户")
    second = make_ku("book-2", "B", "先分析财务模型")
    embeddings = np.array([
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
    ])

    merged = merge_source_preserving_similar_kus([first, second], embeddings, threshold=0.9)

    assert len(merged) == 2
