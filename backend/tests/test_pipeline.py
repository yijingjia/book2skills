"""
核心 Pipeline 单元测试
运行：pytest tests/ -v
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── Parser 测试 ──────────────────────────────────────────────────────────────

class TestDocumentParser:
    def test_is_noise_filters_preface(self):
        from app.pipeline.parser import DocumentParser
        parser = DocumentParser()
        assert parser._is_noise("前言") is True
        assert parser._is_noise("第一章 决策框架") is False
        assert parser._is_noise("参考文献") is True

    def test_split_markdown_by_chapter_markers(self):
        """Chapter boundaries are `第N章` lines, NOT heading levels.
        第3章 has multiple ## sections — they must NOT be split into separate chapters."""
        from app.pipeline.parser import DocumentParser

        parser = DocumentParser()
        # This fixture mirrors real pymupdf4llm output structure
        markdown = "\n\n".join([
            "## PREFACE 再版序",
            "再版序正文内容。" * 30,
            "第1章",
            "## 是非对错的底层逻辑",
            "第一章正文。" * 30,
            "### 一个人心中应该有三种对错观",
            "小节内容。" * 20,
            "### 法学家的对错观",
            "法学家内容。" * 20,
            "第2章",
            "## 思考问题的底层逻辑",
            "第二章正文。" * 30,
            "### 事实、观点、立场和信仰",
            "事实观点内容。" * 20,
            "第3章",
            "## 个体进化的底层逻辑",
            "第三章正文。" * 30,
            "## 人生商业模式=能力×效率×杠杆",
            "商业模式内容。" * 30,
            "### 能力",
            "能力内容。" * 20,
            "## 把工作当成玩",
            "工作当成玩内容。" * 30,
            "## 如何做好时间管理",
            "时间管理内容。" * 30,
        ])

        chapters = parser._split_markdown_into_chapters(markdown)

        # Should have exactly 3 numbered chapters (preface handled separately)
        numbered = [ch for ch in chapters if ch.title.startswith("是非") or ch.title.startswith("思考") or ch.title.startswith("个体")]
        assert len(numbered) == 3, f"Expected 3 chapters, got {len(numbered)}: {[c.title for c in numbered]}"

        # Chapter 1
        ch1 = next(ch for ch in chapters if "是非" in ch.title)
        assert ch1.chapter_num >= 1
        assert "第一章正文" in ch1.text
        assert "法学家内容" in ch1.text

        # Chapter 3: ALL ## sections must be in the same chapter
        ch3 = next(ch for ch in chapters if "个体" in ch.title)
        assert "商业模式内容" in ch3.text, "## 人生商业模式 must stay in chapter 3"
        assert "工作当成玩内容" in ch3.text, "## 把工作当成玩 must stay in chapter 3"
        assert "时间管理内容" in ch3.text, "## 如何做好时间管理 must stay in chapter 3"

    def test_split_markdown_detects_preface_and_afterword(self):
        from app.pipeline.parser import DocumentParser

        parser = DocumentParser()
        markdown = "\n\n".join([
            "## PREFACE 再版序",
            "再版序正文。" * 30,
            "# 初版序 PREFACE",
            "初版序正文。" * 30,
            "第1章",
            "## 是非对错的底层逻辑",
            "正文。" * 50,
            "后记",
            "# 文明，是更高级的生命",
            "后记正文。" * 30,
        ])
        chapters = parser._split_markdown_into_chapters(markdown)
        titles = [ch.title for ch in chapters]

        assert any("再版序" in t or "PREFACE" in t for t in titles), f"Preface not found in {titles}"
        assert any("是非" in t for t in titles), f"Chapter 1 not found in {titles}"
        assert any("后记" in t or "文明" in t for t in titles), f"Afterword not found in {titles}"

    def test_split_markdown_returns_empty_for_no_markers(self):
        from app.pipeline.parser import DocumentParser

        parser = DocumentParser()
        markdown = "这是一段没有任何章节标记的纯文本。" * 50
        chapters = parser._split_markdown_into_chapters(markdown)
        assert chapters == []

    def test_split_markdown_chinese_numeral_chapter_markers(self):
        from app.pipeline.parser import DocumentParser

        parser = DocumentParser()
        markdown = "\n\n".join([
            "第一章",
            "## 开篇",
            "第一章内容。" * 30,
            "第二章",
            "## 发展",
            "第二章内容。" * 30,
        ])
        chapters = parser._split_markdown_into_chapters(markdown)
        assert len(chapters) == 2
        assert "开篇" in chapters[0].title
        assert "发展" in chapters[1].title

    def test_split_markdown_supports_heading_chapter_markers_with_plain_title(self):
        from app.pipeline.parser import DocumentParser

        parser = DocumentParser()
        markdown = "\n\n".join([
            "# 初版序 PREFACE",
            "初版序正文。" * 30,
            "## 第1章",
            "是非对错的底层逻辑",
            "第一章正文。" * 30,
            "## 一个人心中，应该有三种对错观",
            "小节内容。" * 20,
            "## 第2章",
            "## 思考问题的底层逻辑",
            "第二章正文。" * 30,
        ])
        chapters = parser._split_markdown_into_chapters(markdown)

        titles = [ch.title for ch in chapters]
        assert titles == ["初版序 PREFACE", "是非对错的底层逻辑", "思考问题的底层逻辑"]
        assert "第一章正文" in chapters[1].text
        assert "小节内容" in chapters[1].text
        assert "第二章正文" in chapters[2].text

    def test_split_markdown_supports_inline_chapter_title_markers(self):
        from app.pipeline.parser import DocumentParser

        parser = DocumentParser()
        markdown = "\n\n".join([
            "# 前言",
            "前言正文。" * 30,
            "第一章 认知觉醒",
            "第一章正文。" * 30,
            "## 第一节 不要误拆",
            "第一章小节。" * 20,
            "第二章 潜意识——生命留给我们的彩蛋",
            "第二章正文。" * 30,
        ])

        chapters = parser._split_markdown_into_chapters(markdown)

        assert [ch.title for ch in chapters] == [
            "认知觉醒",
            "潜意识——生命留给我们的彩蛋",
        ]
        assert "第一章正文" in chapters[0].text
        assert "第一章小节" in chapters[0].text
        assert "第二章正文" in chapters[1].text

    def test_split_markdown_supports_english_chapter_markers(self):
        from app.pipeline.parser import DocumentParser

        parser = DocumentParser()
        markdown = "\n\n".join([
            "CHAPTER 1 Foundations",
            "Chapter one body. " * 80,
            "## Background",
            "Background body. " * 40,
            "## CHAPTER 2",
            "Systems",
            "Chapter two body. " * 80,
        ])

        chapters = parser._split_markdown_into_chapters(markdown)

        assert [ch.title for ch in chapters] == ["Foundations", "Systems"]
        assert "Background body" in chapters[0].text
        assert "Chapter two body" in chapters[1].text

    def test_split_markdown_ignores_toc_like_chapter_lines(self):
        from app.pipeline.parser import DocumentParser

        parser = DocumentParser()
        markdown = "\n\n".join([
            "目录",
            "第1章 是非对错的底层逻辑 .......... 7",
            "第2章 思考问题的底层逻辑 .......... 23",
            "## 第1章",
            "是非对错的底层逻辑",
            "第一章正文。" * 30,
        ])

        chapters = parser._split_markdown_into_chapters(markdown)

        assert len(chapters) == 1
        assert chapters[0].title == "是非对错的底层逻辑"

    def test_split_markdown_ignores_english_toc_like_chapter_lines(self):
        from app.pipeline.parser import DocumentParser

        parser = DocumentParser()
        markdown = "\n\n".join([
            "Contents",
            "CHAPTER 1 Foundations ........ 7",
            "CHAPTER 2 Systems ........ 23",
            "CHAPTER 1 Foundations",
            "Chapter one body. " * 80,
            "## Background",
            "Background body. " * 40,
            "CHAPTER 2 Systems",
            "Chapter two body. " * 80,
        ])

        chapters = parser._split_markdown_into_chapters(markdown)

        assert [ch.title for ch in chapters] == ["Foundations", "Systems"]
        assert "Chapter one body" in chapters[0].text
        assert "Background body" in chapters[0].text
        assert "Chapter two body" in chapters[1].text

    def test_split_markdown_requires_monotonic_chapter_numbers(self):
        from app.pipeline.parser import DocumentParser

        parser = DocumentParser()
        markdown = "\n\n".join([
            "第1章",
            "开篇",
            "第一章正文。" * 30,
            "第1章",
            "目录页重复标题",
            "这段不应成为新章节。" * 30,
            "第2章",
            "发展",
            "第二章正文。" * 30,
        ])

        chapters = parser._split_markdown_into_chapters(markdown)

        assert [ch.title for ch in chapters] == ["开篇", "发展"]
        assert "目录页重复标题" in chapters[0].text
        assert "第二章正文" in chapters[1].text

    @patch("app.pipeline.parser.pymupdf4llm")
    @patch("app.pipeline.parser.fitz")
    def test_parse_pdf_uses_pymupdf4llm(self, mock_fitz, mock_pymupdf4llm):
        from app.pipeline.parser import DocumentParser

        mock_doc = MagicMock()
        mock_doc.metadata = {"title": "测试书籍", "author": "作者"}
        mock_doc.page_count = 100
        mock_fitz.open.return_value = mock_doc

        mock_pymupdf4llm.to_markdown.side_effect = [
            # First call: full markdown
            "\n\n".join([
                "第1章",
                "## 决策框架",
                "第一章正文内容。" * 30,
                "### 小节一",
                "小节一内容。" * 20,
                "第2章",
                "## 思考方法",
                "第二章正文内容。" * 30,
            ]),
            # Second call: page_chunks mode (list of dicts)
            [
                {"metadata": {"page": 7}, "text": "第1章\n## 决策框架"},
                {"metadata": {"page": 8}, "text": "### 小节一"},
                {"metadata": {"page": 23}, "text": "第2章\n## 思考方法"},
            ],
        ]

        parser = DocumentParser()
        result = parser._parse_pdf("/fake/path.pdf")

        assert result.title == "测试书籍"
        assert result.author == "作者"
        assert result.page_count == 100
        assert result.file_type == "pdf"
        assert len(result.chapters) == 2
        assert "决策框架" in result.chapters[0].title
        assert "第一章正文内容" in result.chapters[0].text
        assert result.chapters[0].page_start == 7
        assert result.chapters[0].page_end == 22   # 23 - 1
        assert "思考方法" in result.chapters[1].title
        assert result.chapters[1].page_start == 23
        assert result.chapters[1].page_end == 100  # last chapter → page_count

    @patch("app.pipeline.parser.pymupdf4llm")
    def test_build_page_index_skips_chunks_without_page_metadata(self, mock_pymupdf4llm):
        from app.pipeline.parser import DocumentParser, RawChapter

        mock_pymupdf4llm.to_markdown.return_value = [
            {"metadata": {"page": None}, "text": "第1章\n## 决策框架"},
            {"metadata": {}, "text": "第2章\n## 思考方法"},
            {"metadata": None, "text": "第2章\n## 思考方法"},
            {"metadata": {"page_number": 7}, "text": "第1章\n## 决策框架"},
            {"metadata": {"page": 23}, "text": "第2章\n## 思考方法"},
        ]
        chapters = [
            RawChapter(chapter_num=1, title="决策框架", text="第一章正文"),
            RawChapter(chapter_num=2, title="思考方法", text="第二章正文"),
        ]

        parser = DocumentParser()
        parser._build_page_index("/fake/path.pdf", chapters, page_count=100)

        assert chapters[0].page_start == 7
        assert chapters[0].page_end == 22
        assert chapters[1].page_start == 23
        assert chapters[1].page_end == 100

    def test_split_markdown_warns_when_large_markdown_has_no_boundaries(self, caplog):
        from app.pipeline.parser import DocumentParser

        parser = DocumentParser()
        markdown = "正文内容。" * 5000

        with caplog.at_level("WARNING"):
            chapters = parser._split_markdown_into_chapters(markdown)

        assert chapters == []
        assert "No chapter boundaries detected" in caplog.text


# ─── KnowledgeUnit 规范化测试 ────────────────────────────────────────────────

def test_knowledge_unit_normalizes_scalar_text_fields():
    from app.schemas.schemas import KnowledgeUnit

    ku = KnowledgeUnit(
        source_chunk_id="book_ch1_0",
        source_chapter_num=1,
        principle=["原则一", "原则二"],
        method={"name": "方法名", "detail": "方法说明"},
        example=["例子一", "例子二"],
    )

    assert ku.principle == "原则一\n原则二"
    assert ku.method == "方法名\n方法说明"
    assert ku.example == "例子一\n例子二"


@pytest.mark.asyncio
async def test_extractor_preserves_ku_with_list_example():
    from app.pipeline.extractor import KnowledgeExtractor
    from app.pipeline.retriever import RetrievedChunk

    payload = [
        {
            "name": "系统思考",
            "definition": "识别要素之间关系的能力",
            "type": "mental_model",
            "principle": ["看见结构", "关注反馈"],
            "method": {"step": "画出关键变量"},
            "example": ["例子 A", "例子 B"],
            "when_to_use": "分析复杂问题",
        }
    ]

    class FakeCompletions:
        async def create(self, **kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))
                    )
                ]
            )

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    extractor = KnowledgeExtractor()
    extractor.client = FakeClient()
    chunks = [
        RetrievedChunk(
            text="复杂系统需要先识别变量关系，再观察反馈。",
            book_id="book-1",
            chapter_num=3,
            chapter_title="系统思考",
            chunk_index=7,
            page_start=42,
            score=0.9,
        )
    ]

    kus = await extractor._call_batch_llm("prompt", chunks)

    assert len(kus) == 1
    assert kus[0].principle == "看见结构\n关注反馈"
    assert kus[0].method == "画出关键变量"
    assert kus[0].example == "例子 A\n例子 B"
    assert kus[0].source_chunk_id == "book-1_ch3_7"
    assert kus[0].source_chapter_num == 3


@pytest.mark.asyncio
async def test_close_llm_client_awaits_close_method():
    from app.core.llm import close_llm_client

    class Client:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    client = Client()
    await close_llm_client(client)
    assert client.closed is True


@pytest.mark.asyncio
async def test_close_llm_client_awaits_aclose_method():
    from app.core.llm import close_llm_client

    class Client:
        def __init__(self):
            self.closed = False

        async def aclose(self):
            self.closed = True

    client = Client()
    await close_llm_client(client)
    assert client.closed is True


@pytest.mark.asyncio
async def test_close_llm_client_ignores_missing_client():
    from app.core.llm import close_llm_client

    await close_llm_client(None)
    await close_llm_client(object())


@pytest.mark.asyncio
async def test_close_embedding_client_closes_inner_client():
    from app.core.llm import close_embedding_client

    class InnerClient:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    class AsyncEmbeddingsResource:
        def __init__(self, inner):
            self._client = inner

    inner = InnerClient()
    embedder = SimpleNamespace(async_client=AsyncEmbeddingsResource(inner))

    await close_embedding_client(embedder)

    assert inner.closed is True


@pytest.mark.asyncio
async def test_close_embedding_client_ignores_none_and_missing():
    from app.core.llm import close_embedding_client

    await close_embedding_client(None)
    await close_embedding_client(object())
    await close_embedding_client(SimpleNamespace(async_client=None))
    await close_embedding_client(SimpleNamespace(async_client=object()))


@pytest.mark.asyncio
async def test_embedding_service_closes_embedding_client():
    from app.pipeline.embedder import EmbeddingService

    service = EmbeddingService.__new__(EmbeddingService)
    service.embeddings = AsyncMock()

    with patch("app.pipeline.embedder.close_embedding_client", new=AsyncMock()) as close:
        await service.aclose()

    close.assert_awaited_once_with(service.embeddings)


@pytest.mark.asyncio
async def test_ku_processor_closes_embedding_client():
    from app.pipeline.ku_processor import KUProcessor

    processor = KUProcessor.__new__(KUProcessor)
    processor.embedder = AsyncMock()

    with patch("app.pipeline.ku_processor.close_embedding_client", new=AsyncMock()) as close:
        await processor.aclose()

    close.assert_awaited_once_with(processor.embedder)


@pytest.mark.asyncio
async def test_cluster_generator_closes_ku_processor_embedder():
    from app.pipeline.cluster_generator import ClusterGenerator

    generator = ClusterGenerator.__new__(ClusterGenerator)
    generator.client = AsyncMock()
    generator.ku_processor = AsyncMock()

    with patch("app.pipeline.cluster_generator.close_llm_client", new=AsyncMock()) as close_llm:
        await generator.aclose()

    close_llm.assert_awaited_once_with(generator.client)
    generator.ku_processor.aclose.assert_awaited_once()


# ─── Chunker 测试 ────────────────────────────────────────────────────────────

class TestDocumentChunker:
    def test_chunk_produces_correct_metadata(self):
        from app.pipeline.chunker import DocumentChunker
        from app.pipeline.parser import RawChapter
        chunker = DocumentChunker(chunk_size=100, chunk_overlap=10)
        chapters = [
            RawChapter(
                chapter_num=1,
                title="决策框架",
                text="这是第一章的内容。" * 20,
                page_start=1,
                page_end=10,
            )
        ]
        chunks = chunker.chunk_chapters(chapters, "test-book-id")
        assert len(chunks) > 0
        assert all(c.book_id == "test-book-id" for c in chunks)
        assert all(c.chapter_num == 1 for c in chunks)
        assert all(c.chapter_title == "决策框架" for c in chunks)

    def test_chunk_respects_size_limit(self):
        from app.pipeline.chunker import DocumentChunker
        from app.pipeline.parser import RawChapter
        chunk_size = 200
        chunker = DocumentChunker(chunk_size=chunk_size, chunk_overlap=20)
        chapters = [
            RawChapter(chapter_num=1, title="测试章节", text="内容很长。" * 100)
        ]
        chunks = chunker.chunk_chapters(chapters, "book-id")
        # 允许少量超出（分隔符原因），但不能超过 2x
        assert all(len(c.text) <= chunk_size * 2 for c in chunks)


# ─── Retriever 测试 ──────────────────────────────────────────────────────────

class TestRAGRetriever:
    @pytest.mark.asyncio
    async def test_returns_low_score_results_when_any_result_exists(self):
        from app.pipeline.retriever import RAGRetriever

        with patch("app.pipeline.retriever.QdrantClient") as mock_qdrant, \
             patch("app.pipeline.retriever.get_embedding_client") as mock_get_embed:

            mock_embed_client = mock_get_embed.return_value
            mock_embed_client.aembed_query = AsyncMock(return_value=[0.1] * 1536)
            # 返回一个低分结果
            low_score_result = MagicMock()
            low_score_result.score = 0.3
            low_score_result.payload = {
                "text": "不相关内容",
                "book_id": "book-id",
                "chapter_num": 1,
                "chapter_title": "章节一",
                "page_start": 1,
            }
            mock_qdrant.return_value.query_points.return_value = MagicMock(
                points=[low_score_result]
            )

            retriever = RAGRetriever()
            chunks = await retriever.retrieve("完全不相关的查询", "book-id", min_score=0.75)
            assert len(chunks) == 1
            assert chunks[0].score == 0.3

    @pytest.mark.asyncio
    async def test_raises_low_confidence_error_when_no_result(self):
        from app.pipeline.retriever import LowConfidenceError, RAGRetriever

        with patch("app.pipeline.retriever.QdrantClient") as mock_qdrant, \
             patch("app.pipeline.retriever.get_embedding_client") as mock_get_embed:

            mock_embed_client = mock_get_embed.return_value
            mock_embed_client.aembed_query = AsyncMock(return_value=[0.1] * 1536)
            mock_qdrant.return_value.query_points.return_value = MagicMock(points=[])

            retriever = RAGRetriever()
            with pytest.raises(LowConfidenceError):
                await retriever.retrieve("完全不相关的查询", "book-id")


# ─── BM25 Reranker 测试 ──────────────────────────────────────────────────────

class TestBM25Reranker:
    def _make_chunk(self, text: str, score: float, idx: int = 0):
        from app.pipeline.retriever import RetrievedChunk
        return RetrievedChunk(
            text=text,
            book_id="book-id",
            chapter_num=1,
            chapter_title="ch",
            chunk_index=idx,
            page_start=None,
            score=score,
        )

    def test_rerank_boosts_keyword_match(self):
        from app.pipeline.reranker import BM25Reranker
        reranker = BM25Reranker()
        query = "redis TTL 过期时间"
        # chunk_a has high vector score but no keywords
        chunk_a = self._make_chunk("这是一段关于缓存系统的介绍，主要讨论存储后端。", score=0.9, idx=0)
        # chunk_b has lower vector score but contains the keyword
        chunk_b = self._make_chunk(
            "Redis 的 TTL（Time To Live）是键过期时间的核心机制，用 EXPIRE 命令设置。",
            score=0.55, idx=1,
        )
        result = reranker.rerank(query, [chunk_a, chunk_b], top_k=2)
        # chunk_b should be ranked first due to BM25 keyword boost
        assert result[0].chunk_index == 1

    def test_rerank_returns_all_when_candidates_lte_top_k(self):
        from app.pipeline.reranker import BM25Reranker
        reranker = BM25Reranker()
        chunks = [self._make_chunk("内容", score=0.8, idx=i) for i in range(3)]
        result = reranker.rerank("查询", chunks, top_k=5)
        assert len(result) == 3

    def test_rerank_empty_input(self):
        from app.pipeline.reranker import BM25Reranker
        assert BM25Reranker().rerank("query", [], top_k=5) == []


# ─── Hybrid Retriever 测试 ───────────────────────────────────────────────────

class TestRAGRetrieverHybrid:
    def _make_point(self, text: str, score: float, idx: int):
        p = MagicMock()
        p.id = idx
        p.score = score
        p.payload = {
            "text": text,
            "book_id": "book-id",
            "chapter_num": 1,
            "chapter_title": "章节一",
            "page_start": 1,
        }
        return p

    @pytest.mark.asyncio
    async def test_hybrid_retrieves_and_reranks(self):
        from app.pipeline.retriever import RAGRetriever

        with patch("app.pipeline.retriever.QdrantClient") as mock_qdrant, \
             patch("app.pipeline.retriever.get_embedding_client") as mock_get_embed:

            mock_embed_client = mock_get_embed.return_value
            mock_embed_client.aembed_query = AsyncMock(return_value=[0.1] * 1536)
            # High-score chunk with no keywords
            p_no_kw = self._make_point("这是一段关于缓存系统的内容，不含关键词。", score=0.9, idx=0)
            # Low-score chunk but contains the keyword
            p_kw = self._make_point(
                "Redis TTL 过期机制：用 EXPIRE 命令设置键的存活时间。",
                score=0.55, idx=1,
            )
            mock_qdrant.return_value.query_points.return_value = MagicMock(
                points=[p_no_kw, p_kw]
            )

            retriever = RAGRetriever()
            chunks = await retriever.retrieve_hybrid(
                query="redis TTL",
                book_id="book-id",
                top_k=2,
                candidate_k=50,
                use_query_expansion=False,
            )
            assert len(chunks) == 2
            # Keyword-matching chunk should be ranked first after BM25 rerank
            assert chunks[0].chunk_index == 1

    @pytest.mark.asyncio
    async def test_hybrid_raises_when_no_candidates(self):
        from app.pipeline.retriever import LowConfidenceError, RAGRetriever

        with patch("app.pipeline.retriever.QdrantClient") as mock_qdrant, \
             patch("app.pipeline.retriever.get_embedding_client") as mock_get_embed:

            mock_embed_client = mock_get_embed.return_value
            mock_embed_client.aembed_query = AsyncMock(return_value=[0.1] * 1536)
            mock_qdrant.return_value.query_points.return_value = MagicMock(points=[])

            retriever = RAGRetriever()
            with pytest.raises(LowConfidenceError):
                await retriever.retrieve_hybrid("找不到的内容", "book-id", use_query_expansion=False)


# ─── QueryExpander 测试 ───────────────────────────────────────────────────────

class TestQueryExpander:
    @pytest.mark.asyncio
    async def test_expand_returns_list_on_success(self):
        from app.pipeline.query_expander import QueryExpander
        with patch("app.pipeline.query_expander.get_llm_client") as mock_client, \
             patch("app.pipeline.query_expander.get_chat_model", return_value="test-model"):
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content='["改写一", "rewrite two", "第三种问法"]'))]
            mock_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
            expander = QueryExpander()
            result = await expander.expand("redis TTL", n=3)
            assert len(result) == 3
            assert "改写一" in result

    @pytest.mark.asyncio
    async def test_expand_returns_empty_on_failure(self):
        from app.pipeline.query_expander import QueryExpander
        with patch("app.pipeline.query_expander.get_llm_client") as mock_client, \
             patch("app.pipeline.query_expander.get_chat_model", return_value="test-model"):
            mock_client.return_value.chat.completions.create = AsyncMock(side_effect=Exception("API error"))
            expander = QueryExpander()
            result = await expander.expand("redis TTL")
            assert result == []


# ─── Packer 测试 ─────────────────────────────────────────────────────────────

class TestSkillPacker:
    def test_pack_creates_valid_zip(self, tmp_path):
        import zipfile

        from app.pipeline.packer import SkillPacker

        ref_dir = tmp_path / "test_book"
        ref_dir.mkdir()
        references = ref_dir / "references"
        references.mkdir()
        (references / "ch01_test.md").write_text("# 第1章\n内容", encoding="utf-8")
        (references / "index.json").write_text('{"chapters": []}', encoding="utf-8")

        packer = SkillPacker()
        zip_path = tmp_path / "skills.zip"
        _ = packer.pack(
            skill_md="# Test Skill\n\n## 工作流\n### 步骤1：测试",
            references_dir=str(ref_dir),
            scripts={"check.py": "print('hello')"},
            templates={"report.md": "# 报告模板"},
            output_path=str(zip_path),
            book_title="测试书籍",
        )

        assert zip_path.exists()
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert "SKILL.md" in names
            assert "manifest.json" in names
            assert "scripts/check.py" in names
            assert "templates/report.md" in names
            assert any(n.startswith("references/") for n in names)


# ─── Asset Generator 测试 ──────────────────────────────────────────────────

class TestAssetGenerator:
    @pytest.mark.asyncio
    async def test_generate_assets_success(self):
        from app.pipeline.asset_generator import AssetGenerator

        with patch("app.pipeline.asset_generator.get_llm_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()

            # 模拟 LLM 返回合乎要求的 JSON 字符串
            mock_json = '''
            {
              "scripts": {
                "test.py": "def main():\\n    return 42"
              },
              "templates": {
                "report.md": "# Test Report"
              }
            }
            '''
            mock_response.choices = [MagicMock(message=MagicMock(content=mock_json))]
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            generator = AssetGenerator()
            scripts, templates = await generator.generate_assets("Test Book", "Workflow", "Context")

            assert "test.py" in scripts
            assert "return 42" in scripts["test.py"]
            assert "report.md" in templates
            assert "# Test Report" in templates["report.md"]

    @pytest.mark.asyncio
    async def test_generate_assets_drops_invalid_python(self):
        from app.pipeline.asset_generator import AssetGenerator

        with patch("app.pipeline.asset_generator.get_llm_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()

            # 模拟 LLM 返回带有语法错误的 Python 脚本
            mock_json = '''
            {
              "scripts": {
                "valid.py": "x = 1",
                "invalid.py": "def main(): \\n return 1 + * 2"
              },
              "templates": {}
            }
            '''
            mock_response.choices = [MagicMock(message=MagicMock(content=mock_json))]
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            generator = AssetGenerator()
            scripts, templates = await generator.generate_assets("Test Book", "Workflow", "Context")

            assert "valid.py" in scripts
            assert "invalid.py" not in scripts  # 应该因为 AST 解析失败被丢弃
            assert len(templates) == 0
