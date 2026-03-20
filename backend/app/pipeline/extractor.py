"""
知识单元 (KU) 提取器 — 第 3 层核心管道
职责：将无结构的 TextChunk 借助设定好的 Prompt 和 LLM Structured Output 转译为高信息密度的 KnowledgeUnit。
"""
import asyncio
import json
from pathlib import Path

from app.core.llm import get_generation_model, get_llm_client
from app.core.retry import llm_retry
from app.pipeline.retriever import RetrievedChunk
from app.schemas.schemas import KnowledgeUnit

# 读取指定的 Prompt 模板
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "extract_knowledge.md"

class KnowledgeExtractor:
    """提取 TextChunk 并在其中剥离出结构化原则和方法的执行器"""

    def __init__(self):
        self.client = get_llm_client()
        with open(PROMPT_PATH, encoding="utf-8") as f:
            self.prompt_template = f.read()

    async def extract_from_chunks(
        self,
        chunks: list[RetrievedChunk],
        max_concurrency: int = 5,
        group_size: int = 3
    ) -> list[KnowledgeUnit]:
        """
        批量从 TextChunks 中提取 KnowledgeUnit。
        将 chunks 分组（默认每组 3 个），每组只调用一次 LLM，显著节省 token 和调用次数。
        """
        import logging
        logger = logging.getLogger(__name__)

        # 将 chunks 按 group_size 分组
        batches = [chunks[i:i + group_size] for i in range(0, len(chunks), group_size)]

        sem = asyncio.Semaphore(max_concurrency)
        processed_chunks = 0
        total_chunks = len(chunks)

        async def _process_batch(batch: list[RetrievedChunk]) -> list[KnowledgeUnit]:
            nonlocal processed_chunks
            async with sem:
                try:
                    results = await self.extract_batch_chunks(batch)
                    processed_chunks += len(batch)
                    logger.info(f"[Extractor] Progress: {processed_chunks}/{total_chunks} ({processed_chunks/total_chunks*100:.1f}%)")
                    return results
                except Exception as e:
                    processed_chunks += len(batch)
                    logger.warning(f"[Extractor Error] Batch 提取失败 (含 {len(batch)} 个 chunks): {e}")
                    return []

        tasks = [_process_batch(b) for b in batches]
        batch_results = await asyncio.gather(*tasks)

        # 展平结果列表
        all_kus = [ku for sublist in batch_results for ku in sublist]
        return all_kus

    async def extract_batch_chunks(self, batch: list[RetrievedChunk]) -> list[KnowledgeUnit]:
        """为一组 chunks 构建批量 Prompt 并调用 LLM"""
        if not batch:
            return []

        # 构建 XML 格式的批量输入
        chunks_xml = "<chunks_batch>\n"
        for i, chunk in enumerate(batch):
            chunks_xml += f'  <chunk id="{i}">{chunk.text}</chunk>\n'
        chunks_xml += "</chunks_batch>"

        # 填充模板
        prompt = self.prompt_template.replace("{{ chapter_title }}", batch[0].chapter_title)
        # 将构造好的 XML 注入模板中的占位符
        prompt = prompt.replace("{{ chunk_text }}", chunks_xml)

        return await self._call_batch_llm(prompt, batch)

    @llm_retry
    async def _call_batch_llm(self, prompt: str, batch: list[RetrievedChunk]) -> list[KnowledgeUnit]:
        """实际的 LLM 调用，处理批量返回的 JSON 数组"""
        response = await self.client.chat.completions.create(
            model=get_generation_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        raw_result = response.choices[0].message.content
        if not raw_result:
            return []

        # 解析 JSON 数组
        try:
            # 兼容处理：有的模型即使要求 json_object 也会返回 {"data": [...]} 这种嵌套
            data_list = json.loads(raw_result)
            if isinstance(data_list, dict):
                # 寻找可能的数组字段
                for val in data_list.values():
                    if isinstance(val, list):
                        data_list = val
                        break

            if not isinstance(data_list, list):
                 raise ValueError(f"LLM 应该返回数组但返回了: {type(data_list)}")
        except Exception as e:
            raise ValueError(f"JSON 解析失败: {e}\nRaw: {raw_result[:200]}")

        # 映射回 KnowledgeUnit
        final_kus = []
        for item in data_list:
            try:
                # 获取并移除映射 ID，防止 Pydantic 报错
                cid_data = item.copy()
                cid_str = str(cid_data.pop("chunk_id", "0"))
                cid = int(cid_str) if cid_str.isdigit() else 0

                # 越界保护
                if cid < 0 or cid >= len(batch):
                    cid = 0

                chunk = batch[cid]

                # 回填源信息到字典（必须在构造前，因为这两个是必填字段）
                cid_data["source_chunk_id"] = f"{chunk.book_id}_ch{chunk.chapter_num}_{chunk.chunk_index}"
                cid_data["source_chapter_num"] = chunk.chapter_num

                # 创建 KU 对象
                ku = KnowledgeUnit(**cid_data)

                if self._is_valid_ku(ku):
                    final_kus.append(ku)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"单个 KU 解析失败: {e}")
                continue

        return final_kus

    def _is_valid_ku(self, ku: KnowledgeUnit | None) -> bool:
        """评估提取出来的 KU 是否有价值，抛除废话"""
        if ku is None:
            return False
        # 只要存在原理说明或具体步骤或方法名，且不为 None，即视为有价值
        if ku.principle and len(str(ku.principle)) > 5:
            return True
        if ku.method and len(str(ku.method)) > 2:
            return True
        if ku.step_by_step and len(ku.step_by_step) > 0:
            return True
        return False
