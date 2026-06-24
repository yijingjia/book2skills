import numpy as np
import pytest

from app.pipeline.cross_book_normalizer import (
    assign_source_ku_ids,
    build_normalization_result,
    build_similarity_candidates,
    ku_normalization_text,
    normalize_cross_book_kus,
)
from app.schemas.schemas import KnowledgeUnit


def make_ku(
    method: str,
    principle: str,
    *,
    book_id: str,
    chapter: int = 1,
    chunk: str = "chunk-1",
) -> KnowledgeUnit:
    return KnowledgeUnit(
        source_chunk_id=chunk,
        source_chapter_num=chapter,
        principle=principle,
        method=method,
        step_by_step=[],
        example=None,
        when_to_use=[],
        source_book_id=book_id,
        source_book_title=f"Book {book_id}",
        source_book_author=None,
        source_books=[
            {
                "book_id": book_id,
                "title": f"Book {book_id}",
                "author": None,
                "chapter_num": chapter,
                "chunk_id": chunk,
                "skill_package_id": None,
            }
        ],
    )


def test_assign_source_ku_ids_is_stable_by_order():
    kus = [make_ku("MVP", "先小步验证", book_id="book-a")]

    wrapped = assign_source_ku_ids(kus)

    assert wrapped[0]["ku_id"] == "ku-0000"
    assert wrapped[0]["ku"].method == "MVP"


def test_ku_normalization_text_contains_method_and_principle():
    ku = make_ku("MVP", "先小步验证", book_id="book-a")

    assert ku_normalization_text(ku) == "MVP 先小步验证"


def test_build_similarity_candidates_only_cross_book_pairs():
    source_kus = assign_source_ku_ids(
        [
            make_ku("MVP", "先小步验证", book_id="book-a"),
            make_ku("MVP", "用最小版本验证需求", book_id="book-b"),
            make_ku("增长模型", "关注获客和留存", book_id="book-a"),
        ]
    )
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.95, 0.05],
            [0.0, 1.0],
        ]
    )

    candidates = build_similarity_candidates(source_kus, embeddings, threshold=0.9)

    assert len(candidates["pairs"]) == 1
    assert candidates["pairs"][0]["from_ku_id"] == "ku-0000"
    assert candidates["pairs"][0]["to_ku_id"] == "ku-0001"
    assert candidates["pairs"][0]["source_book_ids"] == ["book-a", "book-b"]
    assert candidates["pairs"][0]["similarity"] >= 0.9


def test_build_similarity_candidates_skips_same_book_pairs():
    source_kus = assign_source_ku_ids(
        [
            make_ku("MVP", "先小步验证", book_id="book-a"),
            make_ku("MVP", "用最小版本验证需求", book_id="book-a"),
        ]
    )
    embeddings = np.array([[1.0, 0.0], [0.99, 0.01]])

    candidates = build_similarity_candidates(source_kus, embeddings, threshold=0.9)

    assert candidates["pairs"] == []


def test_build_normalization_result_keeps_variants_and_creates_view():
    kus = [
        make_ku("用户访谈", "先访谈用户验证问题", book_id="book-a", chunk="a1"),
        make_ku("问题访谈", "通过访谈确认需求是否真实", book_id="book-b", chunk="b1"),
        make_ku("增长模型", "关注获客 and 留存", book_id="book-c", chunk="c1"),
    ]
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.96, 0.04],
            [0.0, 1.0],
        ]
    )

    result = build_normalization_result(kus, embeddings, threshold=0.9)

    assert len(result.source_kus["knowledge_units"]) == 3
    assert len(result.same_as_edges["edges"]) == 1
    assert result.same_as_edges["edges"][0]["edge_type"] == "same_as"
    assert result.normalized_ku_groups["groups"][0]["member_ku_ids"] == ["ku-0000", "ku-0001"]
    assert len(result.deduped_view_kus) == 2
    assert len(result.deduped_view["knowledge_units"]) == 2
    first_view = result.deduped_view["knowledge_units"][0]
    assert len(first_view["source_books"]) == 2


def test_build_normalization_result_uses_transitive_same_as_groups():
    kus = [
        make_ku("MVP", "先小步验证", book_id="book-a", chunk="a1"),
        make_ku("精益验证", "用最小实验验证需求", book_id="book-b", chunk="b1"),
        make_ku("问题验证", "先验证问题再做方案", book_id="book-c", chunk="c1"),
    ]
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.906, 0.423],
            [0.643, 0.766],
        ]
    )

    result = build_normalization_result(kus, embeddings, threshold=0.9)

    same_group = next(
        group for group in result.normalized_ku_groups["groups"] if group["relationship"] == "same_as"
    )
    assert same_group["member_ku_ids"] == ["ku-0000", "ku-0001", "ku-0002"]
    assert len(result.same_as_edges["edges"]) == 2
    assert len(result.deduped_view_kus) == 1


class FakeEmbedder:
    async def aembed_documents(self, texts):
        assert len(texts) == 2
        return [[1.0, 0.0], [0.97, 0.03]]


@pytest.mark.asyncio
async def test_normalize_cross_book_kus_embeds_texts_once():
    kus = [
        make_ku("用户访谈", "验证问题", book_id="book-a"),
        make_ku("问题访谈", "验证需求", book_id="book-b"),
    ]

    result = await normalize_cross_book_kus(kus, FakeEmbedder(), threshold=0.9)

    assert len(result.same_as_edges["edges"]) == 1
    assert len(result.deduped_view_kus) == 1


def test_normalization_result_exposes_pipeline_artifact_names():
    kus = [
        make_ku("MVP", "验证需求", book_id="book-a"),
        make_ku("MVP", "验证问题", book_id="book-b"),
    ]
    result = build_normalization_result(kus, np.array([[1.0, 0.0], [0.96, 0.04]]), threshold=0.9)

    scripts_payload = {
        "ku_similarity_candidates.json": result.similarity_candidates,
        "normalized_ku_groups.json": result.normalized_ku_groups,
        "same_as_edges.json": result.same_as_edges,
        "deduped_view.json": result.deduped_view,
    }

    assert set(scripts_payload) == {
        "ku_similarity_candidates.json",
        "normalized_ku_groups.json",
        "same_as_edges.json",
        "deduped_view.json",
    }


def _source_ku(ku_id, book_id, method):
    from app.schemas.schemas import KnowledgeUnit

    return {
        "ku_id": ku_id,
        "ku": KnowledgeUnit(
            source_chunk_id=f"{book_id}_ch1_a01",
            source_chapter_num=1,
            method=method,
            source_book_id=book_id,
            source_book_title=f"Book {book_id}",
            source_book_author=None,
            source_books=[{"book_id": book_id, "title": f"Book {book_id}", "chapter_num": 1}],
        ),
    }


def test_build_top_k_similarity_candidates_skips_same_book_and_uses_rank():
    from app.pipeline.cross_book_normalizer import build_top_k_similarity_candidates

    source_kus = [
        _source_ku("ku-0000", "book-a", "费曼技巧"),
        _source_ku("ku-0001", "book-b", "打好比方的方法"),
        _source_ku("ku-0002", "book-a", "费曼技巧的另一种说法"),
        _source_ku("ku-0003", "book-b", "时间管理"),
    ]
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.82, 0.18],
            [0.99, 0.01],
            [0.0, 1.0],
        ]
    )

    result = build_top_k_similarity_candidates(source_kus, embeddings, top_k=1)

    pairs = result["pairs"]
    assert len(pairs) == 2
    assert pairs[0]["from_ku_id"] == "ku-0000"
    assert pairs[0]["to_ku_id"] == "ku-0001"
    assert all(
        set(pair["source_book_ids"]) == {"book-a", "book-b"}
        for pair in pairs
    )


def test_build_normalization_result_from_candidates_uses_confirmed_judgments_only():
    from app.pipeline.cross_book_normalizer import build_normalization_result_from_candidates

    kus = [
        _source_ku("ku-0000", "book-a", "费曼技巧")["ku"],
        _source_ku("ku-0001", "book-b", "打好比方的方法")["ku"],
        _source_ku("ku-0002", "book-b", "时间管理")["ku"],
    ]
    source_kus = [
        _source_ku("ku-0000", "book-a", "费曼技巧"),
        _source_ku("ku-0001", "book-b", "打好比方的方法"),
        _source_ku("ku-0002", "book-b", "时间管理"),
    ]
    candidates = {
        "pairs": [
            {
                "candidate_id": "cand-ku-0000-ku-0001",
                "from_ku_id": "ku-0000",
                "to_ku_id": "ku-0001",
                "similarity": 0.56,
                "source_book_ids": ["book-a", "book-b"],
            },
            {
                "candidate_id": "cand-ku-0000-ku-0002",
                "from_ku_id": "ku-0000",
                "to_ku_id": "ku-0002",
                "similarity": 0.55,
                "source_book_ids": ["book-a", "book-b"],
            },
        ]
    }
    judgments = {
        "judgments": [
            {
                "candidate_id": "cand-ku-0000-ku-0001",
                "from_ku_id": "ku-0000",
                "to_ku_id": "ku-0001",
                "decision": "same_as",
                "confidence": 0.86,
                "evidence": "两者都要求用简单类比解释复杂概念。",
                "decided_by": "backend_llm",
            },
            {
                "candidate_id": "cand-ku-0000-ku-0002",
                "from_ku_id": "ku-0000",
                "to_ku_id": "ku-0002",
                "decision": "related_but_distinct",
                "confidence": 0.72,
                "evidence": "同属学习主题，但操作对象不同。",
                "decided_by": "backend_llm",
            },
        ]
    }

    result = build_normalization_result_from_candidates(
        kus=kus,
        source_kus=source_kus,
        candidates=candidates,
        judgments=judgments,
    )

    assert len(result.same_as_edges["edges"]) == 1
    assert result.same_as_edges["edges"][0]["edge_type"] == "same_as"
    assert result.same_as_edges["edges"][0]["confidence"] == 0.86
    assert len(result.same_as_judgments["judgments"]) == 2
    same_groups = [
        group for group in result.normalized_ku_groups["groups"]
        if group["relationship"] == "same_as"
    ]
    assert same_groups[0]["member_ku_ids"] == ["ku-0000", "ku-0001"]
    assert len(result.deduped_view["knowledge_units"]) == 2


def test_build_normalization_result_from_candidates_handles_malformed_judgments():
    from app.pipeline.cross_book_normalizer import build_normalization_result_from_candidates

    kus = [
        _source_ku("ku-0000", "book-a", "费曼技巧")["ku"],
        _source_ku("ku-0001", "book-b", "打好比方的方法")["ku"],
    ]
    source_kus = [
        _source_ku("ku-0000", "book-a", "费曼技巧"),
        _source_ku("ku-0001", "book-b", "打好比方的方法"),
    ]
    candidates = {
        "pairs": [
            {
                "candidate_id": "cand-ku-0000-ku-0001",
                "from_ku_id": "ku-0000",
                "to_ku_id": "ku-0001",
                "similarity": 0.56,
                "source_book_ids": ["book-a", "book-b"],
            }
        ]
    }
    # One valid judgment, one missing from_ku_id, one missing to_ku_id
    judgments = {
        "judgments": [
            {
                "candidate_id": "cand-ku-0000-ku-0001",
                "from_ku_id": "ku-0000",
                "to_ku_id": "ku-0001",
                "decision": "same_as",
                "confidence": 0.86,
            },
            {
                "candidate_id": "cand-ku-0000-ku-0001",
                "to_ku_id": "ku-0001",
                "decision": "same_as",
            },
            {
                "candidate_id": "cand-ku-0000-ku-0001",
                "from_ku_id": "ku-0000",
                "decision": "same_as",
            },
        ]
    }

    result = build_normalization_result_from_candidates(
        kus=kus,
        source_kus=source_kus,
        candidates=candidates,
        judgments=judgments,
    )

    # The malformed ones should be filtered out without causing crash, only 1 valid same_as edge is made.
    assert len(result.same_as_edges["edges"]) == 1
    assert result.same_as_edges["edges"][0]["from_ku_id"] == "ku-0000"
    assert result.same_as_edges["edges"][0]["to_ku_id"] == "ku-0001"


def test_build_normalization_result_from_candidates_deduplicates_judgments():
    from app.pipeline.cross_book_normalizer import build_normalization_result_from_candidates

    kus = [
        _source_ku("ku-0000", "book-a", "费曼技巧")["ku"],
        _source_ku("ku-0001", "book-b", "打好比方的方法")["ku"],
    ]
    source_kus = [
        _source_ku("ku-0000", "book-a", "费曼技巧"),
        _source_ku("ku-0001", "book-b", "打好比方的方法"),
    ]
    candidates = {
        "pairs": [
            {
                "candidate_id": "cand-ku-0000-ku-0001",
                "from_ku_id": "ku-0000",
                "to_ku_id": "ku-0001",
                "similarity": 0.56,
                "source_book_ids": ["book-a", "book-b"],
            }
        ]
    }
    # Duplicate judgments for the same candidate pair.
    judgments = {
        "judgments": [
            {
                "candidate_id": "cand-ku-0000-ku-0001",
                "from_ku_id": "ku-0000",
                "to_ku_id": "ku-0001",
                "decision": "same_as",
                "confidence": 0.86,
            },
            {
                "candidate_id": "cand-ku-0000-ku-0001",
                "from_ku_id": "ku-0000",
                "to_ku_id": "ku-0001",
                "decision": "same_as",
                "confidence": 0.90,
            },
        ]
    }

    result = build_normalization_result_from_candidates(
        kus=kus,
        source_kus=source_kus,
        candidates=candidates,
        judgments=judgments,
    )

    # Should only result in one same_as edge.
    assert len(result.same_as_edges["edges"]) == 1
    # Check that it kept the first one (confidence 0.86)
    assert result.same_as_edges["edges"][0]["confidence"] == 0.86

