"""
BM25 重排器 — 对向量检索候选集做关键词相关性重排
解决"关键词存在但因长句稀释导致语义距离偏大"的召回问题
"""
import logging
import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from app.pipeline.retriever import RetrievedChunk

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    """
    Lightweight tokenizer supporting CJK + Latin.
    CJK characters are split individually; Latin words are lowercased and split on boundaries.
    """
    tokens = re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]|[a-zA-Z0-9]+", text.lower())
    return tokens if tokens else [text.lower()]


@dataclass
class _ScoredChunk:
    chunk: RetrievedChunk
    vector_score: float    # normalized vector similarity
    bm25_score: float      # normalized BM25 keyword score
    hybrid_score: float    # weighted combination


class BM25Reranker:
    """
    BM25 关键词重排器。

    对向量检索返回的候选集同时计算向量分数和 BM25 分数，
    按加权混合分排序后返回 top_k。关键词权重越高越能拯救
    "关键词存在但语义相似度低"的 chunk。
    """

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int,
        vector_weight: float = 0.6,
        bm25_weight: float = 0.4,
    ) -> list[RetrievedChunk]:
        """
        对候选 chunks 做 BM25 + 向量分数混合重排。

        Args:
            query: 原始查询文本（用于 BM25 计分）
            chunks: 向量检索的候选集
            top_k: 最终返回数量
            vector_weight: 向量相似度权重（默认 0.6）
            bm25_weight: BM25 关键词权重（默认 0.4）

        Returns:
            重排后的 top_k 个 chunks，按 hybrid_score 降序
        """
        if not chunks:
            return []
        if len(chunks) <= top_k:
            # Candidate pool is small; still rerank for correct ordering
            actual_top_k = len(chunks)
        else:
            actual_top_k = top_k

        tokenized_corpus = [_tokenize(c.text) for c in chunks]
        tokenized_query = _tokenize(query)

        bm25 = BM25Okapi(tokenized_corpus)
        raw_bm25_scores = bm25.get_scores(tokenized_query)

        # Normalize BM25 scores to [0, 1]. BM25 can return all zeros for tiny
        # candidate pools, so fall back to direct query-token overlap.
        max_bm25 = max(raw_bm25_scores) if max(raw_bm25_scores) > 0 else 0.0
        if max_bm25 > 0:
            normalized_bm25 = [float(s) / max_bm25 for s in raw_bm25_scores]
        else:
            query_terms = set(tokenized_query)
            overlap_scores = [
                len(query_terms.intersection(tokens)) / len(query_terms)
                if query_terms
                else 0.0
                for tokens in tokenized_corpus
            ]
            max_overlap = max(overlap_scores) if max(overlap_scores) > 0 else 1.0
            normalized_bm25 = [float(s) / max_overlap for s in overlap_scores]

        # Normalize vector scores to [0, 1]
        vector_scores = [c.score for c in chunks]
        max_vec = max(vector_scores) if max(vector_scores) > 0 else 1.0
        normalized_vec = [s / max_vec for s in vector_scores]

        scored = [
            _ScoredChunk(
                chunk=chunk,
                vector_score=v,
                bm25_score=b,
                hybrid_score=vector_weight * v + bm25_weight * b,
            )
            for chunk, v, b in zip(chunks, normalized_vec, normalized_bm25)
        ]

        scored.sort(key=lambda x: x.hybrid_score, reverse=True)

        logger.debug(
            "BM25Reranker: %d candidates -> top %d  "
            "top hybrid=%.3f (vec=%.3f bm25=%.3f)",
            len(chunks),
            actual_top_k,
            scored[0].hybrid_score if scored else 0,
            scored[0].vector_score if scored else 0,
            scored[0].bm25_score if scored else 0,
        )

        return [s.chunk for s in scored[:actual_top_k]]
