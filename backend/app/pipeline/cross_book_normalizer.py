from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity  # type: ignore[import-untyped]

from app.schemas.schemas import KnowledgeUnit

CONFIRMED_SAME_AS_DECISIONS = {"same_as", "alias_of"}


def _candidate_id(left_id: str, right_id: str) -> str:
    return f"cand-{left_id}-{right_id}"



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
    ku_book_ids = [_book_ids_for_ku(item["ku"]) for item in source_kus]
    pairs = []
    for left_index, left in enumerate(source_kus):
        left_books = ku_book_ids[left_index]
        for right_index in range(left_index + 1, len(source_kus)):
            right = source_kus[right_index]
            right_books = ku_book_ids[right_index]
            if left_books & right_books:
                continue
            similarity = float(similarities[left_index, right_index])
            if similarity < threshold:
                continue
            pairs.append(
                {
                    "candidate_id": _candidate_id(left["ku_id"], right["ku_id"]),
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
    same_as_judgments: dict[str, list[dict[str, Any]]]
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


def build_top_k_similarity_candidates(
    source_kus: list[dict[str, Any]],
    embeddings: np.ndarray,
    top_k: int,
    min_similarity: float = 0.35,
) -> dict[str, list[dict[str, Any]]]:
    """Return each KU's top-k cross-book neighbors as candidate same_as pairs."""
    if len(source_kus) <= 1:
        return {"pairs": []}

    similarities = cosine_similarity(embeddings)
    ku_book_ids = [_book_ids_for_ku(item["ku"]) for item in source_kus]
    seen: set[tuple[str, str]] = set()
    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(source_kus):
        left_books = ku_book_ids[left_index]
        ranked: list[tuple[float, int, dict[str, Any]]] = []
        for right_index, right in enumerate(source_kus):
            if left_index == right_index:
                continue
            right_books = ku_book_ids[right_index]
            if left_books & right_books:
                continue
            similarity = float(similarities[left_index, right_index])
            if similarity < min_similarity:
                continue
            ranked.append((similarity, right_index, right))

        for similarity, right_index, right in sorted(ranked, key=lambda item: item[0], reverse=True)[:top_k]:
            left_id = left["ku_id"]
            right_id = right["ku_id"]
            ordered = tuple(sorted([left_id, right_id]))
            if ordered in seen:
                continue
            seen.add(ordered)
            source_book_ids = sorted(left_books | ku_book_ids[right_index])
            pairs.append(
                {
                    "candidate_id": _candidate_id(ordered[0], ordered[1]),
                    "from_ku_id": ordered[0],
                    "to_ku_id": ordered[1],
                    "similarity": round(similarity, 6),
                    "source_book_ids": source_book_ids,
                }
            )
    return {"pairs": pairs}


def _judgment_key(judgment: dict[str, Any]) -> tuple[str, str] | None:
    from_id = judgment.get("from_ku_id")
    to_id = judgment.get("to_ku_id")
    if not from_id or not to_id:
        return None
    sorted_ids = sorted([str(from_id), str(to_id)])
    return (sorted_ids[0], sorted_ids[1])


def _confirmed_judgment_pairs(judgments: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [
        judgment
        for judgment in judgments.get("judgments", [])
        if judgment.get("decision") in CONFIRMED_SAME_AS_DECISIONS
    ]


def build_normalization_result_from_candidates(
    *,
    kus: list[KnowledgeUnit],
    source_kus: list[dict[str, Any]],
    candidates: dict[str, list[dict[str, Any]]],
    judgments: dict[str, list[dict[str, Any]]],
) -> CrossBookNormalizationResult:
    """Build normalization artifacts from candidate pairs plus external judgments."""
    if not kus:
        return CrossBookNormalizationResult(
            source_kus={"knowledge_units": []},
            similarity_candidates={"pairs": []},
            same_as_judgments={"judgments": []},
            normalized_ku_groups={"groups": []},
            same_as_edges={"edges": []},
            deduped_view={"knowledge_units_count": 0, "knowledge_units": []},
            deduped_view_kus=[],
        )

    source_by_id = {item["ku_id"]: item["ku"] for item in source_kus}
    candidate_by_key = {
        tuple(sorted([pair["from_ku_id"], pair["to_ku_id"]])): pair
        for pair in candidates.get("pairs", [])
    }
    confirmed_pairs = _confirmed_judgment_pairs(judgments)
    confirmed = []
    seen_keys = set()
    for judgment in confirmed_pairs:
        key = _judgment_key(judgment)
        if key is not None and key in candidate_by_key:
            if key not in seen_keys:
                seen_keys.add(key)
                confirmed.append(judgment)

    components = _connected_components(source_kus, confirmed)

    edges = []
    for judgment in confirmed:
        key = _judgment_key(judgment)
        assert key is not None
        pair = candidate_by_key[key]
        edge_type = "same_as" if judgment.get("decision") == "same_as" else "alias_of"
        edges.append(
            {
                "edge_id": f"{edge_type}-{key[0]}-{key[1]}",
                "edge_type": edge_type,
                "from_ku_id": key[0],
                "to_ku_id": key[1],
                "confidence": float(judgment.get("confidence", pair.get("similarity", 0.0))),
                "evidence": judgment.get("evidence") or "same_as_judge",
                "status": "confirmed",
                "review_required": False,
                "decided_by": judgment.get("decided_by", "backend_llm"),
                "candidate_id": pair.get("candidate_id"),
            }
        )

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
        same_as_judgments={"judgments": judgments.get("judgments", [])},
        normalized_ku_groups={"groups": groups},
        same_as_edges={"edges": edges},
        deduped_view={
            "knowledge_units_count": len(deduped_kus),
            "knowledge_units": [ku.model_dump() for ku in deduped_kus],
        },
        deduped_view_kus=deduped_kus,
    )


def build_normalization_result(
    kus: list[KnowledgeUnit],
    embeddings: np.ndarray,
    threshold: float = 0.9,
) -> CrossBookNormalizationResult:
    if not kus:
        return build_normalization_result_from_candidates(
            kus=[],
            source_kus=[],
            candidates={"pairs": []},
            judgments={"judgments": []},
        )

    source_kus = assign_source_ku_ids(kus)
    candidates = build_similarity_candidates(source_kus, embeddings, threshold)
    judgments = {
        "judgments": [
            {
                "candidate_id": pair.get("candidate_id") or _candidate_id(pair["from_ku_id"], pair["to_ku_id"]),
                "from_ku_id": pair["from_ku_id"],
                "to_ku_id": pair["to_ku_id"],
                "decision": "same_as",
                "confidence": pair["similarity"],
                "evidence": "embedding_similarity",
                "decided_by": "embedding_threshold",
            }
            for pair in candidates["pairs"]
        ]
    }
    return build_normalization_result_from_candidates(
        kus=kus,
        source_kus=source_kus,
        candidates=candidates,
        judgments=judgments,
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
