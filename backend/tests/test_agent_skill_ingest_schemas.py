import pytest
from pydantic import ValidationError

from app.schemas.schemas import (
    AgentKnowledgeUnit,
    AgentKnowledgeUnitIngestRequest,
    AgentSkillIngestRequest,
    SkillStep,
)


def test_skill_step_rejects_empty_source_quote():
    with pytest.raises(ValidationError):
        SkillStep(
            step_num=1,
            action="提出问题假设",
            source_quote="",
            source_chapter="第 1 章",
        )

    with pytest.raises(ValidationError):
        SkillStep(
            step_num=1,
            action="提出问题假设",
            source_quote="   ",
            source_chapter="第 1 章",
        )


def test_agent_skill_ingest_request_requires_source_quotes():
    with pytest.raises(ValidationError):
        AgentSkillIngestRequest.model_validate(
            {
                "router_md": "# Router",
                "skills": [
                    {
                        "name": "Customer_Discovery",
                        "description": "Validate whether a customer problem is real.",
                        "when_to_use": ["需要验证用户问题"],
                        "thinking_steps": [
                            {
                                "step_num": 1,
                                "action": "提出问题假设",
                                "source_quote": "",
                                "source_chapter": "第 1 章",
                            }
                        ],
                        "references_keywords": ["customer discovery"],
                    }
                ],
            }
        )


def test_agent_knowledge_unit_requires_source_quote_and_content():
    unit = AgentKnowledgeUnit(
        source_chapter_num=2,
        source_quote="系统由要素、连接关系和目标构成。",
        principle="系统不是要素相加，而是关系和目标共同作用。",
    )

    assert unit.source_chapter_num == 2
    assert unit.principle.startswith("系统")


def test_agent_knowledge_unit_rejects_empty_content():
    with pytest.raises(ValidationError):
        AgentKnowledgeUnit(source_chapter_num=2, source_quote="原文")


def test_agent_knowledge_unit_ingest_requires_non_empty_units():
    with pytest.raises(ValidationError):
        AgentKnowledgeUnitIngestRequest(knowledge_units=[])
