from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.core.llm import close_llm_client, get_chat_model, get_llm_client
from app.core.retry import llm_retry

logger = logging.getLogger(__name__)

VALID_DECISIONS = {
    "same_as",
    "alias_of",
    "related_but_distinct",
    "contextual_overlap",
    "not_same",
}


def extract_judgment_items(raw: Any) -> list[dict[str, Any]]:
    """Accept standard JSON, qwen-style nested list values, or a top-level array."""
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if not isinstance(raw, dict):
        return []
    if isinstance(raw.get("judgments"), list):
        return [item for item in raw["judgments"] if isinstance(item, dict)]
    if isinstance(raw.get("data"), list):
        return [item for item in raw["data"] if isinstance(item, dict)]
    items = []
    for value in raw.values():
        if isinstance(value, list):
            items.extend([item for item in value if isinstance(item, dict)])
    return items


def normalize_judge_response(
    raw: Any,
    candidates: dict[str, list[dict[str, Any]]],
    decided_by: str,
) -> dict[str, list[dict[str, Any]]]:
    candidate_by_id = {
        str(pair["candidate_id"]): pair
        for pair in candidates.get("pairs", [])
        if pair.get("candidate_id")
    }
    normalized = []
    for item in extract_judgment_items(raw):
        candidate_id = str(item.get("candidate_id") or "")
        pair = candidate_by_id.get(candidate_id)
        if not pair:
            continue
        decision = str(item.get("decision") or "not_same")
        if decision not in VALID_DECISIONS:
            decision = "not_same"
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(confidence, 1.0))
        evidence = str(item.get("evidence") or "").strip()
        normalized.append(
            {
                "candidate_id": candidate_id,
                "from_ku_id": pair["from_ku_id"],
                "to_ku_id": pair["to_ku_id"],
                "decision": decision,
                "confidence": confidence,
                "evidence": evidence,
                "decided_by": decided_by,
            }
        )
    return {"judgments": normalized}


def _ku_by_id(source_kus: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["ku_id"]): item
        for item in source_kus.get("knowledge_units", [])
        if item.get("ku_id")
    }


def _batch_prompt(source_kus: dict[str, Any], pairs: list[dict[str, Any]]) -> str:
    by_id = _ku_by_id(source_kus)
    pair_payload = []
    for pair in pairs:
        left = by_id[pair["from_ku_id"]]
        right = by_id[pair["to_ku_id"]]
        pair_payload.append(
            {
                "candidate_id": pair["candidate_id"],
                "from_ku": {
                    "ku_id": pair["from_ku_id"],
                    "method": left.get("method"),
                    "principle": left.get("principle"),
                    "step_by_step": left.get("step_by_step"),
                    "example": left.get("example"),
                    "when_to_use": left.get("when_to_use"),
                    "source_books": left.get("source_books"),
                },
                "to_ku": {
                    "ku_id": pair["to_ku_id"],
                    "method": right.get("method"),
                    "principle": right.get("principle"),
                    "step_by_step": right.get("step_by_step"),
                    "example": right.get("example"),
                    "when_to_use": right.get("when_to_use"),
                    "source_books": right.get("source_books"),
                },
                "similarity": pair.get("similarity"),
            }
        )
    return json.dumps({"pairs": pair_payload}, ensure_ascii=False)


class KUSameAsJudge:
    def __init__(self, batch_size: int = 30):
        self.batch_size = batch_size
        self.client = get_llm_client()

    async def aclose(self) -> None:
        await close_llm_client(self.client)

    async def judge(
        self,
        source_kus: dict[str, Any],
        candidates: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        pairs = candidates.get("pairs", [])
        logger.info(f"Starting LLM judgment for {len(pairs)} pairs with batch size {self.batch_size}")
        tasks = []
        for index in range(0, len(pairs), self.batch_size):
            batch = pairs[index : index + self.batch_size]
            tasks.append(self._judge_batch(source_kus, {"pairs": batch}))
        
        results = await asyncio.gather(*tasks)
        all_judgments = []
        for res in results:
            all_judgments.extend(res["judgments"])
        
        logger.info(f"Completed judgment for {len(pairs)} pairs, generated {len(all_judgments)} judgments")
        return {"judgments": all_judgments}

    @llm_retry
    async def _judge_batch(
        self,
        source_kus: dict[str, Any],
        candidates: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        pairs = candidates.get("pairs", [])
        logger.info(f"Judging batch with {len(pairs)} pairs")
        
        system_prompt = (
            "你是一个跨书籍知识单元（KU）归一化评审器。判断每对 KU 是否表达同一个或相关的方法、原则或步骤。\n"
            "只输出 JSON 格式的对象，不要包含任何额外的描述或 Markdown 标记。格式如下：\n"
            "{\n"
            "  \"judgments\": [\n"
            "    {\n"
            "      \"candidate_id\": \"候选对 ID（字符串类型）\",\n"
            "      \"decision\": \"必须是以下五个枚举值之一：'same_as'、'alias_of'、'related_but_distinct'、'contextual_overlap'、'not_same'\",\n"
            "      \"confidence\": \"置信度，介于 0.0 到 1.0 之间的浮点数\",\n"
            "      \"evidence\": \"为什么给出该决策的理由或证据\"\n"
            "    }\n"
            "  ]\n"
            "}"
        )
        
        response = await self.client.chat.completions.create(
            model=get_chat_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": _batch_prompt(source_kus, pairs)},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        content = response.choices[0].message.content or "{}"
        try:
            raw = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {content}. Error: {e}")
            raw = {}
        return normalize_judge_response(raw, candidates, decided_by="backend_llm")
