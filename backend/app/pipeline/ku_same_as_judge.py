from __future__ import annotations

import json
from typing import Any

from app.core.llm import get_chat_model, get_llm_client

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
    for value in raw.values():
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


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

    async def judge(
        self,
        source_kus: dict[str, Any],
        candidates: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        all_judgments = []
        pairs = candidates.get("pairs", [])
        for index in range(0, len(pairs), self.batch_size):
            batch = pairs[index : index + self.batch_size]
            raw = await self._judge_batch(source_kus, {"pairs": batch})
            all_judgments.extend(raw["judgments"])
        return {"judgments": all_judgments}

    async def _judge_batch(
        self,
        source_kus: dict[str, Any],
        candidates: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        response = await self.client.chat.completions.create(
            model=get_chat_model(),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是跨书知识归一化评审器。判断每对 KU 是否表达同一个方法、原则 or 步骤。"
                        "只输出 JSON，格式为 {\"judgments\": [...]}. "
                        "decision 只能 be same_as, alias_of, related_but_distinct, contextual_overlap, not_same。"
                    ),
                },
                {"role": "user", "content": _batch_prompt(source_kus, candidates.get("pairs", []))},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        content = response.choices[0].message.content or "{}"
        try:
            raw = json.loads(content)
        except json.JSONDecodeError:
            raw = {}
        return normalize_judge_response(raw, candidates, decided_by="backend_llm")
