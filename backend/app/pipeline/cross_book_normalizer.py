from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from app.schemas.schemas import KnowledgeUnit


def ku_normalization_text(ku: KnowledgeUnit) -> str:
    """Return a canonical text string used to embed this KU for similarity comparison."""
    parts = []
    if ku.method:
        parts.append(ku.method)
    if ku.principle:
        parts.append(ku.principle)
    if ku.step_by_step:
        parts.append("; ".join(ku.step_by_step))
    if ku.example:
        parts.append(ku.example)
    if ku.when_to_use:
        parts.append("; ".join(ku.when_to_use))
    return " ".join(parts).strip() or "Unknown Concept"


def _book_ids_for_ku(ku: KnowledgeUnit) -> set[str]:
    # NOTE: unions source_book_id and source_books[*].book_id. If both are set
    # and inconsistent, the KU is tagged as belonging to both books (conservative).
    ids = {str(source.get("book_id")) for source in ku.source_books or [] if source.get("book_id")}
    if ku.source_book_id:
        ids.add(str(ku.source_book_id))
    return ids


def assign_source_ku_ids(kus: list[KnowledgeUnit]) -> list[dict[str, Any]]:
    """Wrap each KU with a positional ID string (e.g. 'ku-0000'). IDs are ephemeral within a single normalization run and must not be persisted across runs."""
    return [{"ku_id": f"ku-{index:04d}", "ku": ku} for index, ku in enumerate(kus)]


def build_similarity_candidates(
    source_kus: list[dict[str, Any]],
    embeddings: np.ndarray,
    threshold: float,
) -> dict[str, list[dict[str, Any]]]:
    """Return cross-book candidate pairs whose embedding cosine similarity exceeds threshold."""
    if len(source_kus) <= 1:
        return {"pairs": []}

    similarities = cosine_similarity(embeddings)
    pairs = []
    for left_index, left in enumerate(source_kus):
        left_books = _book_ids_for_ku(left["ku"])
        for right_index in range(left_index + 1, len(source_kus)):
            right = source_kus[right_index]
            right_books = _book_ids_for_ku(right["ku"])
            if left_books & right_books:
                continue
            similarity = float(similarities[left_index, right_index])
            if similarity < threshold:
                continue
            pairs.append(
                {
                    "from_ku_id": left["ku_id"],
                    "to_ku_id": right["ku_id"],
                    "similarity": round(similarity, 6),
                    "source_book_ids": sorted(left_books | right_books),
                }
            )
    return {"pairs": pairs}


@dataclass
class CrossBookNormalizationResult:
    source_kus: dict[str, Any]
    similarity_candidates: dict[str, list[dict[str, Any]]]
    normalized_ku_groups: dict[str, list[dict[str, Any]]]
    same_as_edges: dict[str, list[dict[str, Any]]]
    deduped_view: dict[str, Any]
    deduped_view_kus: list[KnowledgeUnit]


def _content_length(ku: KnowledgeUnit) -> int:
    return len(ku.method or "") + len(ku.principle or "") + len(str(ku.step_by_step or []))


def _dedupe_source_books(kus: list[KnowledgeUnit]) -> list[dict[str, Any]]:
    seen: set[tuple[str | None, int | None, str | None]] = set()
    result = []
    for ku in kus:
        for source in ku.source_books or []:
            key = (source.get("book_id"), source.get("chapter_num"), source.get("chunk_id"))
            if key in seen:
                continue
            seen.add(key)
            result.append(source)
    return result


def _canonical_ku(members: list[KnowledgeUnit]) -> KnowledgeUnit:
    canonical = max(members, key=_content_length)
    payload = canonical.model_dump()
    payload["source_books"] = _dedupe_source_books(members)
    return KnowledgeUnit(**payload)


def _connected_components(source_kus: list[dict[str, Any]], pairs: list[dict[str, Any]]) -> list[list[str]]:
    parent = {item["ku_id"]: item["ku_id"] for item in source_kus}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for pair in pairs:
        union(pair["from_ku_id"], pair["to_ku_id"])

    groups: dict[str, list[str]] = defaultdict(list)
    for item in source_kus:
        groups[find(item["ku_id"])].append(item["ku_id"])
    return [sorted(ids) for ids in groups.values()]


def build_normalization_result(
    kus: list[KnowledgeUnit],
    embeddings: np.ndarray,
    threshold: float = 0.9,
) -> CrossBookNormalizationResult:
    """Run blocking + grouping on pre-computed embeddings and return all normalization artifacts."""
    if not kus:
        return CrossBookNormalizationResult(
            source_kus={"knowledge_units": []},
            similarity_candidates={"pairs": []},
            normalized_ku_groups={"groups": []},
            same_as_edges={"edges": []},
            deduped_view={"knowledge_units_count": 0, "knowledge_units": []},
            deduped_view_kus=[],
        )

    source_kus = assign_source_ku_ids(kus)
    source_by_id = {item["ku_id"]: item["ku"] for item in source_kus}
    candidates = build_similarity_candidates(source_kus, embeddings, threshold)
    pairs = candidates["pairs"]
    components = _connected_components(source_kus, pairs)

    edges = [
        {
            "edge_id": f"same-{pair['from_ku_id']}-{pair['to_ku_id']}",
            "edge_type": "same_as",
            "from_ku_id": pair["from_ku_id"],
            "to_ku_id": pair["to_ku_id"],
            "confidence": pair["similarity"],
            "evidence": "embedding_similarity",
            "status": "candidate",
            "review_required": False,
        }
        for pair in pairs
    ]

    groups = []
    deduped_kus = []
    for index, member_ids in enumerate(components):
        members = [source_by_id[member_id] for member_id in member_ids]
        canonical = _canonical_ku(members)
        deduped_kus.append(canonical)
        groups.append(
            {
                "group_id": f"group-{index:04d}",
                "canonical_ku_id": max(member_ids, key=lambda member_id: _content_length(source_by_id[member_id])),
                "member_ku_ids": member_ids,
                "source_book_ids": sorted(set().union(*[_book_ids_for_ku(member) for member in members])),
                "relationship": "same_as" if len(member_ids) > 1 else "singleton",
            }
        )

    return CrossBookNormalizationResult(
        source_kus={"knowledge_units": [{"ku_id": item["ku_id"], **item["ku"].model_dump()} for item in source_kus]},
        similarity_candidates=candidates,
        normalized_ku_groups={"groups": groups},
        same_as_edges={"edges": edges},
        deduped_view={
            "knowledge_units_count": len(deduped_kus),
            "knowledge_units": [ku.model_dump() for ku in deduped_kus],
        },
        deduped_view_kus=deduped_kus,
    )


async def normalize_cross_book_kus(
    kus: list[KnowledgeUnit],
    embedder,
    threshold: float = 0.9,
) -> CrossBookNormalizationResult:
    if not kus:
        return build_normalization_result([], np.array([]), threshold=threshold)
    texts = [ku_normalization_text(ku) for ku in kus]
    if hasattr(embedder, "aembed_documents"):
        embeddings = await embedder.aembed_documents(texts)
    else:
        embeddings = [await embedder.aembed_query(text) for text in texts]
    return build_normalization_result(kus, np.array(embeddings), threshold=threshold)
