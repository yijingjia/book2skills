import pytest
from pydantic import ValidationError

from app.schemas.schemas import AgentSkillIngestRequest, SkillStep


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
