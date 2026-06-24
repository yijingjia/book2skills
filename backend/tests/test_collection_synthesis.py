from app.pipeline.collection_synthesis import (
    build_candidate_tension_artifacts,
    build_consensus_artifacts,
)
from app.schemas.schemas import KnowledgeUnit


def ku(method: str, book_id: str, title: str) -> KnowledgeUnit:
    return KnowledgeUnit(
        source_chunk_id=f"{book_id}-chunk",
        source_chapter_num=1,
        method=method,
        principle=f"{method} principle",
        source_books=[{"book_id": book_id, "title": title, "chapter_num": 1, "chunk_id": f"{book_id}-chunk"}],
    )


def test_build_consensus_artifacts_scores_cross_book_themes():
    groups = [("MVP", "desc", [ku("MVP", "a", "A"), ku("MVP", "b", "B")])]

    artifacts = build_consensus_artifacts(groups, total_books=3)

    assert artifacts[0]["theme"] == "MVP"
    assert artifacts[0]["supporting_book_count"] == 2
    assert artifacts[0]["confidence"] == 0.67


def test_build_candidate_tension_artifacts_returns_empty_for_single_book_theme():
    groups = [("MVP", "desc", [ku("MVP", "a", "A")])]

    assert build_candidate_tension_artifacts(groups) == []
