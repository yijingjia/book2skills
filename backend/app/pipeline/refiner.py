"""
对话精炼模块 — 用户通过对话迭代调整 SKILL.md
防幻觉：精炼时仍基于原书 RAG 检索，不自由发挥
"""
from collections.abc import AsyncGenerator

from app.core.config import settings
from app.core.llm import get_chat_model, get_llm_client
from app.core.retry import llm_retry
from app.pipeline.retriever import RAGRetriever
from app.pipeline.skill_generator import SkillGenerator

REFINE_SYSTEM_PROMPT = """你是一个技能精炼助手，帮助用户改进 AI Agent 技能定义（SKILL.md）。

## 绝对规则
1. 所有修改必须基于 <book_context> 中提供的原文内容
2. 不得增加原文中不存在的步骤或建议
3. 每个修改后的步骤仍必须保留 source_quote（原文引用）
4. 如果用户要求添加原文中不存在的内容，礼貌拒绝并说明原因

## 当前技能定义
<current_skill>
{current_skill_md}
</current_skill>

## 相关原文内容
<book_context>
{context}
</book_context>

请根据用户的精炼指令修改技能定义，输出完整的修改后 SKILL.md 内容。"""


class SkillRefiner:
    """对话式技能精炼，基于 RAG 检索确保内容来源于原书"""

    def __init__(self):
        self.client = get_llm_client()
        self.retriever = RAGRetriever()
        self.skill_generator = SkillGenerator()

    async def refine_stream(
        self,
        book_id: str,
        current_skill_md: str,
        instruction: str,
        conversation_history: list[dict],
    ) -> AsyncGenerator[str, None]:
        """
        流式返回精炼后的 SKILL.md。

        Args:
            book_id: 书籍 ID（用于 RAG 检索）
            current_skill_md: 当前的 SKILL.md 内容
            instruction: 用户的精炼指令
            conversation_history: 对话历史

        Yields:
            流式文本片段
        """
        # 根据用户指令检索相关原文（检索失败时降级，不阻断流程）
        try:
            chunks = await self._retrieve_with_retry(
                query=instruction, book_id=book_id
            )
            context = "\n\n---\n\n".join(
                f"[{c.chapter_title}]\n{c.text}" for c in chunks
            )
        except Exception:
            context = "（未检索到直接相关内容，请基于现有技能内容进行调整）"

        system_prompt = REFINE_SYSTEM_PROMPT.format(
            current_skill_md=current_skill_md,
            context=context,
        )

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation_history[-10:])
        messages.append({"role": "user", "content": instruction})

        # stream=True 的 LLM 调用本身不需要 retry（流已打开则不会超时）
        # 但建立连接时可能触发 429，因此用 retry 包住 create() 调用
        stream = await self._create_stream(messages)

        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    @llm_retry
    async def _retrieve_with_retry(self, query: str, book_id: str):
        """Hybrid RAG retrieval with tenacity retry: wider pool + BM25 rerank."""
        return await self.retriever.retrieve_hybrid(
            query=query,
            book_id=book_id,
            top_k=settings.RETRIEVAL_TOP_K,
        )

    @llm_retry
    async def _create_stream(self, messages: list[dict]):
        """建立 SSE 流连接，带 tenacity 重试（仅重试建立连接阶段）"""
        return await self.client.chat.completions.create(
            model=get_chat_model(),
            messages=messages,
            temperature=0.2,
            stream=True,
        )
