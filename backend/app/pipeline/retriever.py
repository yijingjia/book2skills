"""
RAG 检索器 — 从 Qdrant 检索相关段落
Phase 1: 宽召回软阈值
Phase 2: 混合检索（向量 + BM25 重排 + 可选 Query 扩展）
"""
import asyncio
import logging
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.core.config import settings
from app.core.llm import close_embedding_client, get_embedding_client

logger = logging.getLogger(__name__)

DEFAULT_RETRIEVAL_TOP_K = getattr(settings, "RETRIEVAL_TOP_K", 5)
DEFAULT_RETRIEVAL_CANDIDATE_K = getattr(settings, "RETRIEVAL_CANDIDATE_K", 50)
DEFAULT_RETRIEVAL_MIN_SCORE = getattr(settings, "RETRIEVAL_MIN_SCORE", 0.0)
DEFAULT_RETRIEVAL_USE_QUERY_EXPANSION = getattr(
    settings, "RETRIEVAL_USE_QUERY_EXPANSION", False
)
DEFAULT_RETRIEVAL_VECTOR_WEIGHT = getattr(settings, "RETRIEVAL_VECTOR_WEIGHT", 0.6)
DEFAULT_RETRIEVAL_BM25_WEIGHT = getattr(settings, "RETRIEVAL_BM25_WEIGHT", 0.4)
DEFAULT_RETRIEVAL_QUERY_EXPANSION_N = getattr(
    settings, "RETRIEVAL_QUERY_EXPANSION_N", 3
)


class LowConfidenceError(Exception):
    """当检索结果为空时抛出"""
    def __init__(self, score: float, threshold: float, query: str):
        self.score = score
        self.threshold = threshold
        self.query = query
        super().__init__(
            f"Query '{query[:50]}' max similarity {score:.3f} < threshold {threshold:.3f}. "
            "本书未找到相关内容。"
        )


@dataclass
class RetrievedChunk:
    text: str
    book_id: str
    chapter_num: int
    chapter_title: str
    chunk_index: int
    page_start: int | None
    score: float


class RAGRetriever:
    """从 Qdrant 检索相关段落，优先保证召回"""

    def __init__(self):
        self.embeddings = get_embedding_client()
        self.qdrant = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
        )

    async def aclose(self) -> None:
        await close_embedding_client(self.embeddings)

    async def retrieve(
        self,
        query: str,
        book_id: str,
        top_k: int | None = None,
        min_score: float | None = None,
        chapter_nums: list[int] | None = None,
    ) -> list[RetrievedChunk]:
        """
        检索相关段落。

        Args:
            query: 查询文本
            book_id: 书籍 ID（对应 Qdrant collection）
            top_k: 返回最多 K 个结果
            min_score: 最低相似度阈值（可选软过滤）
            chapter_nums: 可选，限定检索的章节范围

        Returns:
            按相似度降序排列的段落列表

        Raises:
            LowConfidenceError: 没有任何检索结果时
        """
        resolved_top_k = top_k if top_k is not None else DEFAULT_RETRIEVAL_TOP_K
        resolved_min_score = (
            min_score if min_score is not None else DEFAULT_RETRIEVAL_MIN_SCORE
        )

        query_vector = await self.embeddings.aembed_query(query)

        # 可选：按章节过滤
        qdrant_filter = None
        if chapter_nums:
            qdrant_filter = Filter(
                should=[
                    FieldCondition(key="chapter_num", match=MatchValue(value=num))
                    for num in chapter_nums
                ]
            )

        response = self.qdrant.query_points(
            collection_name=book_id,
            query=query_vector,
            limit=resolved_top_k,
            query_filter=qdrant_filter,
            with_payload=True,
            score_threshold=0.0,  # 检索阶段不做硬阈值过滤，优先保证召回
        )
        results = response.points

        if not results:
            raise LowConfidenceError(0.0, resolved_min_score, query)

        # 软过滤：优先召回；若过滤后为空则回退到原始结果，避免“有结果但被阈值清空”
        filtered_results = [r for r in results if r.score >= resolved_min_score]
        selected_results = filtered_results or results

        return [
            RetrievedChunk(
                text=r.payload["text"],
                book_id=r.payload["book_id"],
                chapter_num=r.payload["chapter_num"],
                chapter_title=r.payload["chapter_title"],
                chunk_index=r.id,
                page_start=r.payload.get("page_start"),
                score=r.score,
            )
            for r in selected_results
        ]

    async def retrieve_hybrid(
        self,
        query: str,
        book_id: str,
        top_k: int | None = None,
        candidate_k: int | None = None,
        min_score: float | None = None,
        chapter_nums: list[int] | None = None,
        use_query_expansion: bool | None = None,
        vector_weight: float | None = None,
        bm25_weight: float | None = None,
    ) -> list[RetrievedChunk]:
        """
        混合检索：宽向量召回 → 可选 Query 扩展 → BM25 关键词重排 → top_k 结果。

        解决"关键词存在但因长句语义稀释导致向量相似度偏低"的核心召回问题：
          1. 先用较大的 candidate_k 做向量检索，保证候选池足够宽
          2. 若启用 query expansion，用 LLM 生成同义改写并 union 候选集
          3. 用 BM25 对候选集重排，拉升含关键词但向量分偏低的 chunk

        Args:
            query: 查询文本
            book_id: 书籍 ID
            top_k: 最终返回结果数
            candidate_k: 向量检索候选池大小（应远大于 top_k）
            min_score: 软阈值（0.0 表示不过滤）
            chapter_nums: 可选章节范围过滤
            use_query_expansion: 是否用 LLM 扩展查询
            vector_weight: 向量分权重
            bm25_weight: BM25 分权重

        Returns:
            按混合分降序排列的 top_k 个 chunks

        Raises:
            LowConfidenceError: 所有查询均无任何结果时
        """
        resolved_top_k = top_k if top_k is not None else DEFAULT_RETRIEVAL_TOP_K
        resolved_candidate_k = (
            candidate_k
            if candidate_k is not None
            else DEFAULT_RETRIEVAL_CANDIDATE_K
        )
        resolved_min_score = (
            min_score if min_score is not None else DEFAULT_RETRIEVAL_MIN_SCORE
        )
        resolved_use_query_expansion = (
            use_query_expansion
            if use_query_expansion is not None
            else DEFAULT_RETRIEVAL_USE_QUERY_EXPANSION
        )
        resolved_vector_weight = (
            vector_weight
            if vector_weight is not None
            else DEFAULT_RETRIEVAL_VECTOR_WEIGHT
        )
        resolved_bm25_weight = (
            bm25_weight if bm25_weight is not None else DEFAULT_RETRIEVAL_BM25_WEIGHT
        )

        # lazy import to avoid circular dependencies at module load time
        from app.pipeline.query_expander import QueryExpander
        from app.pipeline.reranker import BM25Reranker

        # 1. Build query list (original + optional expansions)
        queries = [query]
        if resolved_use_query_expansion:
            expander = QueryExpander()
            expanded = await expander.expand(query, n=DEFAULT_RETRIEVAL_QUERY_EXPANSION_N)
            queries.extend(expanded)
            logger.info(
                "retrieve_hybrid: expanded query into %d variants for %r",
                len(queries),
                query[:60],
            )

        # 2. Dense vector search for all queries; union by chunk_index, keep highest score
        seen: dict = {}
        tasks = [
            self._dense_search(q, book_id, resolved_candidate_k, chapter_nums)
            for q in queries
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                continue
            for c in r:
                key = c.chunk_index
                if key not in seen or c.score > seen[key].score:
                    seen[key] = c

        candidates = list(seen.values())
        if not candidates:
            raise LowConfidenceError(0.0, resolved_min_score, query)

        logger.info(
            "retrieve_hybrid: %d candidate chunks after union (queries=%d)",
            len(candidates),
            len(queries),
        )

        # 3. BM25 rerank: boost keyword-matching chunks within the candidate pool
        reranker = BM25Reranker()
        final = reranker.rerank(
            query=query,
            chunks=candidates,
            top_k=resolved_top_k,
            vector_weight=resolved_vector_weight,
            bm25_weight=resolved_bm25_weight,
        )
        return final

    async def _dense_search(
        self,
        query: str,
        book_id: str,
        top_k: int,
        chapter_nums: list[int] | None = None,
    ) -> list[RetrievedChunk]:
        """Pure dense vector search without score filtering (internal helper)."""
        query_vector = await self.embeddings.aembed_query(query)

        qdrant_filter = None
        if chapter_nums:
            qdrant_filter = Filter(
                should=[
                    FieldCondition(key="chapter_num", match=MatchValue(value=num))
                    for num in chapter_nums
                ]
            )

        response = self.qdrant.query_points(
            collection_name=book_id,
            query=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
            score_threshold=0.0,
        )
        results = response.points
        if not results:
            raise LowConfidenceError(0.0, 0.0, query)

        return [
            RetrievedChunk(
                text=r.payload["text"],
                book_id=r.payload["book_id"],
                chapter_num=r.payload["chapter_num"],
                chapter_title=r.payload["chapter_title"],
                chunk_index=r.id,
                page_start=r.payload.get("page_start"),
                score=r.score,
            )
            for r in results
        ]

    async def retrieve_by_chapter(
        self,
        book_id: str,
        chapter_num: int,
        query: str,
        max_chunks: int = 12,
    ) -> list["RetrievedChunk"]:
        """用语义搜索从指定章节召回高价值段落。

        提示: 如果要对多章节相同 query 更高效地检索，请使用 retrieve_by_chapter_vec
        对同一 query 开头 embed 一次，再并行调用 retrieve_by_chapter_vec。
        """
        query_vector = await self.embeddings.aembed_query(query)
        return await self.retrieve_by_chapter_vec(
            book_id=book_id,
            chapter_num=chapter_num,
            query_vector=query_vector,
            max_chunks=max_chunks,
        )

    async def retrieve_by_chapter_vec(
        self,
        book_id: str,
        chapter_num: int,
        query_vector: list[float],
        max_chunks: int = 12,
    ) -> list["RetrievedChunk"]:
        """使用预计算的向量语义搜索指定章节高价值段落。

        适合关联多章节时只 embed 一次再并行调用的场景。
        """
        chapter_filter = Filter(
            must=[FieldCondition(key="chapter_num", match=MatchValue(value=chapter_num))]
        )

        response = self.qdrant.query_points(
            collection_name=book_id,
            query=query_vector,
            query_filter=chapter_filter,
            limit=max_chunks,
            with_payload=True,
            score_threshold=0.0,
        )

        return [
            RetrievedChunk(
                text=r.payload["text"],
                book_id=r.payload["book_id"],
                chapter_num=r.payload["chapter_num"],
                chapter_title=r.payload["chapter_title"],
                chunk_index=r.id,
                page_start=r.payload.get("page_start"),
                score=r.score,
            )
            for r in response.points
        ]


@dataclass
class RetrievedSkill:
    skill_id: str
    book_id: str
    skill_package_id: str
    name: str
    description: str
    score: float


class SkillRetriever:
    """从 Qdrant 检索相关技能进行推演组装"""

    def __init__(self):
        self.embeddings = get_embedding_client()
        self.qdrant = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
        )
        self.collection_name = "skills_vectors"

    async def retrieve(
        self,
        query: str,
        top_k: int = 8,
        book_id: str | None = None,
    ) -> list[RetrievedSkill]:
        """
        检索相关技能。

        Args:
            query: 用户提问或面临的场景困境
            top_k: 返回最多 K 个最匹配的技能
            book_id: 可选，限定只在某本书下检索（用于单书推演场景）

        Returns:
            按相关性降序排列的技能列表
        """
        query_vector = await self.embeddings.aembed_query(query)

        # 可选：按书本过滤
        qdrant_filter = None
        if book_id:
            qdrant_filter = Filter(
                should=[
                    FieldCondition(key="book_id", match=MatchValue(value=book_id))
                ]
            )

        # 如果库刚刚起步并且还没创建 vector collection，避免崩溃
        if not self.qdrant.collection_exists(self.collection_name):
            return []

        response = self.qdrant.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
            score_threshold=0.25,  # 放宽召回，后续由提示词与工作流约束精度
        )
        results = response.points

        return [
            RetrievedSkill(
                skill_id=r.id,
                book_id=r.payload.get("book_id", ""),
                skill_package_id=r.payload.get("skill_package_id", ""),
                name=r.payload.get("name", ""),
                description=r.payload.get("description", ""),
                score=r.score,
            )
            for r in results
        ]
