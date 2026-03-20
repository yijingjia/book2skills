"""
Query 扩展器 — 用 LLM 为查询生成多个同义改写
解决"用户措辞与索引用词不一致（缩写/别名/换句话说）"导致的漏召回问题
"""
import json
import logging

from app.core.llm import get_chat_model, get_llm_client

logger = logging.getLogger(__name__)

_EXPAND_PROMPT = """\
你是一个检索优化助手。请为以下查询生成 {n} 个语义等价但措辞不同的改写版本，以提高文档召回率。

改写要求：
1. 保留核心语义，不添加无关内容
2. 可适当扩展缩写、添加同义词或换一种问法
3. 如原查询是中文，部分改写可使用英文关键词（对英文技术术语效果更好）
4. 只输出一个合法的 JSON 字符串数组，不要输出任何解释，例如：
   ["改写1", "改写2", "改写3"]

原始查询：{query}"""


class QueryExpander:
    """
    LLM 驱动的 Query 扩展器。

    在向量检索前生成多个等价查询，union 后喂给向量库，
    大幅提升缩写/别名/跨语言场景的召回率。
    失败时静默返回空列表，上层自动回退到原始 query。
    """

    def __init__(self):
        self.client = get_llm_client()

    async def expand(self, query: str, n: int = 3) -> list[str]:
        """
        生成 n 个改写查询。

        Args:
            query: 原始查询文本
            n: 期望的改写数量（实际数量可能少于 n）

        Returns:
            改写查询列表（不含原始 query），失败时返回 []
        """
        try:
            response = await self.client.chat.completions.create(
                model=get_chat_model(),
                messages=[
                    {
                        "role": "user",
                        "content": _EXPAND_PROMPT.format(query=query, n=n),
                    }
                ],
                temperature=0.3,
                max_tokens=300,
            )
            raw = response.choices[0].message.content.strip()
            # Robustly extract the JSON array even if the model adds extra text
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start == -1 or end == 0:
                logger.warning("QueryExpander: no JSON array found in response for query=%r", query[:60])
                return []
            expanded: list = json.loads(raw[start:end])
            result = [q.strip() for q in expanded if isinstance(q, str) and q.strip()]
            logger.info(
                "QueryExpander: %d expansions for query=%r -> %s",
                len(result),
                query[:60],
                result,
            )
            return result
        except Exception as exc:
            logger.warning("QueryExpander failed for query=%r: %s", query[:60], exc)
            return []
