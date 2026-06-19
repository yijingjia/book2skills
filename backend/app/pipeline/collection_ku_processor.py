import asyncio

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from app.schemas.schemas import KnowledgeUnit


def _ku_text(ku: KnowledgeUnit) -> str:
    parts = []
    if ku.method:
        parts.append(ku.method)
    if ku.principle:
        parts.append(ku.principle)
    if ku.step_by_step:
        parts.append("; ".join(ku.step_by_step))
    return " ".join(parts) if parts else "Unknown Concept"


def _dedup_sources(sources: list[dict]) -> list[dict]:
    seen: set[tuple[str | None, int | None, str | None]] = set()
    result = []
    for source in sources:
        key = (
            source.get("book_id"),
            source.get("chapter_num"),
            source.get("chunk_id"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result


def _content_length(ku: KnowledgeUnit) -> int:
    return len(ku.principle or "") + len(ku.method or "") + len(str(ku.step_by_step))


def _merge_two_kus(first: KnowledgeUnit, second: KnowledgeUnit) -> KnowledgeUnit:
    canonical = first if _content_length(first) >= _content_length(second) else second
    payload = canonical.model_dump()
    payload["source_books"] = _dedup_sources(list(first.source_books or []) + list(second.source_books or []))
    return KnowledgeUnit(**payload)


def merge_source_preserving_similar_kus(
    kus: list[KnowledgeUnit],
    embeddings: np.ndarray,
    threshold: float = 0.9,
) -> list[KnowledgeUnit]:
    if len(kus) <= 1:
        return kus

    sim_matrix = cosine_similarity(embeddings)
    keep_indices = set(range(len(kus)))
    merged_by_index: dict[int, KnowledgeUnit] = {idx: ku for idx, ku in enumerate(kus)}

    for i in range(len(kus)):
        if i not in keep_indices:
            continue
        for j in range(i + 1, len(kus)):
            if j not in keep_indices:
                continue
            if sim_matrix[i, j] >= threshold:
                merged_by_index[i] = _merge_two_kus(merged_by_index[i], merged_by_index[j])
                keep_indices.remove(j)

    return [merged_by_index[idx] for idx in sorted(keep_indices)]


async def semantic_deduplicate_kus(
    kus: list[KnowledgeUnit],
    embedder,
    threshold: float = 0.9,
) -> list[KnowledgeUnit]:
    if len(kus) <= 1:
        return kus
    texts = [_ku_text(ku) for ku in kus]
    if hasattr(embedder, "aembed_documents"):
        embeddings = await embedder.aembed_documents(texts)
    else:
        sem = asyncio.Semaphore(10)

        async def _embed(text: str):
            async with sem:
                return await embedder.aembed_query(text)

        embeddings = await asyncio.gather(*[_embed(text) for text in texts])
    return merge_source_preserving_similar_kus(kus, np.array(embeddings), threshold=threshold)
