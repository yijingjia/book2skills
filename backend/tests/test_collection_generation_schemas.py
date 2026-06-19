from app.schemas.schemas import GenerateCollectionSkillRequest, KnowledgeUnit


def test_generate_collection_skill_request_defaults():
    request = GenerateCollectionSkillRequest()

    assert request.reuse_extracted_kus is True
    assert request.detect_conflicts is True
    assert request.user_goal is None


def test_knowledge_unit_accepts_collection_source_metadata():
    ku = KnowledgeUnit(
        source_chunk_id="chunk-1",
        source_chapter_num=2,
        principle="先验证需求再扩张",
        source_book_id="book-1",
        source_book_title="产品书 A",
        source_book_author="Author A",
        source_books=[
            {
                "book_id": "book-1",
                "title": "产品书 A",
                "author": "Author A",
                "chapter_num": 2,
                "chunk_id": "chunk-1",
            }
        ],
    )

    assert ku.source_book_id == "book-1"
    assert ku.source_books[0]["title"] == "产品书 A"
