"""
核心 Pipeline 单元测试
运行：pytest tests/ -v
"""
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

    def test_clean_page_text_removes_short_lines(self):
        from app.pipeline.parser import DocumentParser
        parser = DocumentParser()
        text = "正文内容这是一段很长的文字内容应该保留\n3\n版权信息"
        result = parser._clean_page_text(text)
        assert "正文内容" in result
        assert "3\n" not in result


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
