import numpy as np
import pytest

from app.pipeline.ku_processor import KUProcessor
from app.schemas.schemas import KnowledgeUnit


def ku(principle: str) -> KnowledgeUnit:
    return KnowledgeUnit(source_chunk_id=principle, source_chapter_num=1, principle=principle)


@pytest.mark.asyncio
async def test_process_and_cluster_can_skip_internal_dedup(monkeypatch):
    processor = KUProcessor()
    kus = [ku("same idea A"), ku("same idea B")]

    async def fake_embeddings(texts):
        return np.array([[1.0, 0.0], [1.0, 0.0]])

    def fake_cluster(input_kus, embeddings):
        assert len(input_kus) == 2
        return [(0, input_kus)]

    monkeypatch.setattr(processor, "_get_embeddings", fake_embeddings)
    monkeypatch.setattr(processor, "cluster_kus_hdbscan", fake_cluster)

    result = await processor.process_and_cluster(kus, deduplicate=False)

    assert len(result[0][1]) == 2
