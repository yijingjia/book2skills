import asyncio
import json
import logging

from app.core.llm import close_llm_client, get_chat_model, get_llm_client
from app.core.retry import llm_retry
from app.pipeline.ku_processor import KUProcessor
from app.schemas.schemas import KnowledgeUnit

logger = logging.getLogger(__name__)


class ClusterGenerator:
    """负责将大量独立的 KnowledgeUnit 进行向量降维聚类，并由大模型提炼主题"""

    def __init__(self):
        self.client = get_llm_client()
        self.model = get_chat_model()
        self.ku_processor = KUProcessor()

    async def aclose(self) -> None:
        await close_llm_client(self.client)
        await self.ku_processor.aclose()

    async def cluster_knowledge_units(
        self, kus: list[KnowledgeUnit]
    ) -> list[tuple[str, str, list[KnowledgeUnit]]]:
        """
        对已萃取出的 KUs 进行意图聚类。
        流程: 去重 -> UMAP降维 -> HDBSCAN聚类 -> LLM主题提取

        Returns:
            返回聚类分组，结构为: [(主题名, 主题描述, 属于该主题的 KUs 列表), ...]
        """
        if not kus:
            return []

        if len(kus) <= 3:
            return [("Core_Methodology", "通用核心方法论与法则", kus)]

        # 1. 数学运算：向量化 -> 去重 -> 降维 -> 聚类
        clustered_groups = await self.ku_processor.process_and_cluster(kus)

        # 2. 对每个聚类簇，并发调用大模型提取 Theme Name 和 Summary
        sem = asyncio.Semaphore(5)
        final_groups = []

        async def _extract_theme(cluster_id: int, cluster_kus: list[KnowledgeUnit]):
            if not cluster_kus:
                return None

            # HDBSCAN 噪声点（cluster_id=-1）语义离散，无法提炼一致主题，直接降级处理
            if cluster_id == -1:
                logger.info(f"Noise cluster detected ({len(cluster_kus)} KUs). Skipping LLM call.")
                return ("Misc_Knowledge", "HDBSCAN 噪声点汇总，语义较为分散", cluster_kus)

            # 构建供模型阅读的 payload
            ku_summaries = []
            for i, ku in enumerate(cluster_kus[:15]):
                method_preview = ku.method
                if ku.step_by_step and isinstance(ku.step_by_step, list) and len(ku.step_by_step) > 0:
                    method_preview = f"{ku.method} (步骤: {ku.step_by_step[0][:20]}...)"
                summary = f"[{i}] 原理: {ku.principle}\n方法: {method_preview}"
                ku_summaries.append(summary)

            payload = "\n\n".join(ku_summaries)

            prompt = f"""These knowledge units belong to one common topic.
Please analyze them and provide:
1. `theme_name`: A specific, professional English name for this topic (e.g., Problem_Solving_Framework, not just General_Method). Use underscores for spaces.
2. `theme_description`: A 1-2 sentence description of what this theme covers.

Data:
{payload}

You must return ONLY a JSON object in this format:
{{"theme_name": "...", "theme_description": "..."}}
"""

            async with sem:
                try:
                    data = await self._call_theme_llm(prompt)
                    theme_name = data.get("theme_name", f"Theme_{cluster_id}")
                    theme_desc = data.get("theme_description", "No description provided.")
                    return (theme_name, theme_desc, cluster_kus)
                except Exception as e:
                    logger.warning(f"Theme extraction failed for cluster {cluster_id}: {e}")
                    return (f"Fallback_Theme_{cluster_id}", "自动聚类的算法分组", cluster_kus)

        # 并发执行所有簇的主题提取
        tasks = [_extract_theme(cid, ckus) for cid, ckus in clustered_groups]
        results = await asyncio.gather(*tasks)

        final_groups = [r for r in results if r is not None]
        return final_groups

    @llm_retry
    async def _call_theme_llm(self, prompt: str) -> dict:
        """实际的 LLM 调用，使用 tenacity retry 装饰"""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
