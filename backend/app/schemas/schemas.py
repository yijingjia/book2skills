import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# ─── Book Schemas ───────────────────────────────────────────────────────────

class BookListResponse(BaseModel):
    book_id: uuid.UUID
    title: str | None
    author: str | None
    status: str
    page_count: int | None
    created_at: datetime
    skill_id: uuid.UUID | None
    skill_status: str | None

    class Config:
        from_attributes = True


class BookUploadResponse(BaseModel):
    book_id: uuid.UUID
    message: str = "Upload successful, processing started"
    is_duplicate: bool = False


class BookStatusResponse(BaseModel):
    book_id: uuid.UUID
    status: str
    title: str | None
    author: str | None
    page_count: int | None
    error_message: str | None
    created_at: datetime


class ChapterResponse(BaseModel):
    id: uuid.UUID
    chapter_num: int
    title: str
    page_start: int | None
    page_end: int | None

    class Config:
        from_attributes = True


class BookDetailResponse(BaseModel):
    book_id: uuid.UUID
    title: str | None
    author: str | None
    status: str
    chapters: list[ChapterResponse]

    class Config:
        from_attributes = True


# ─── Collection Schemas ─────────────────────────────────────────────────────

class CollectionBookSummary(BaseModel):
    book_id: uuid.UUID
    title: str | None
    author: str | None
    status: str
    page_count: int | None
    order_index: int


class CollectionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    book_ids: list[uuid.UUID] = Field(..., min_length=2)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("collection name cannot be blank")
        return v.strip()

    @field_validator("book_ids")
    @classmethod
    def book_ids_must_be_unique(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(v)) != len(v):
            raise ValueError("book_ids must be unique")
        return v


class CollectionUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None
    book_ids: list[uuid.UUID] | None = None

    @field_validator("name")
    @classmethod
    def optional_name_must_not_be_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("collection name cannot be blank")
        return v.strip() if v is not None else None

    @field_validator("book_ids")
    @classmethod
    def optional_book_ids_must_be_unique(
        cls,
        v: list[uuid.UUID] | None,
    ) -> list[uuid.UUID] | None:
        if v is None:
            return None
        if len(v) < 2:
            raise ValueError("a collection requires at least two books")
        if len(set(v)) != len(v):
            raise ValueError("book_ids must be unique")
        return v


class CollectionListResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: str
    book_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CollectionDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: str
    books: list[CollectionBookSummary]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CollectionSkillPackageResponse(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    skill_md: str | None
    scripts: dict | None
    templates: dict | None
    zip_path: str | None = None
    version: int
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── 5-Layer Pipeline Core Schemas ─────────────────────────────────────────────

class KnowledgeUnit(BaseModel):
    """从 Chunk 提取的原子知识单元 (Step 3: Extractor 产物)"""
    source_chunk_id: str
    source_chapter_num: int
    principle: str | None = Field(None, description="核心原理")
    method: str | None = Field(None, description="方法或框架名称")
    step_by_step: list[str] = Field(default_factory=list, description="具体操作步骤")
    example: str | None = Field(None, description="书中案例")
    when_to_use: list[str] = Field(default_factory=list, description="适用场景")

    source_book_id: str | None = Field(None, description="来源书籍 ID，多书生成时使用")
    source_book_title: str | None = Field(None, description="来源书名，多书生成时使用")
    source_book_author: str | None = Field(None, description="来源作者，多书生成时使用")
    source_books: list[dict[str, Any]] = Field(default_factory=list, description="跨书去重后的来源集合")

    @model_validator(mode="before")
    @classmethod
    def handle_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # Handle plural form: "principles" -> "principle"
        if "principles" in data and "principle" not in data:
            principles = data["principles"]
            if isinstance(principles, list) and len(principles) > 0:
                data["principle"] = "\n".join(principles) if isinstance(principles[0], str) else str(principles)
            elif isinstance(principles, str):
                data["principle"] = principles

        # Handle other common field names the LLM may return instead of "principle"
        if not data.get("principle"):
            for alias in ("description", "core_principle", "summary", "insight", "rule"):
                if alias in data and data[alias]:
                    data["principle"] = data[alias]
                    break

        return data

    @field_validator("principle", "method", "example", mode="before")
    @classmethod
    def ensure_optional_string(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            parts = [
                str(item).strip()
                for item in v.values()
                if item is not None and str(item).strip()
            ]
            return "\n".join(parts) or None
        if isinstance(v, (list, tuple, set)):
            parts = [
                str(item).strip()
                for item in v
                if item is not None and str(item).strip()
            ]
            return "\n".join(parts) or None
        return str(v)

    @field_validator("step_by_step", "when_to_use", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, dict):
            return [str(val) for val in v.values()]
        if not isinstance(v, (list, tuple, set)):
            return [str(v)]
        return [str(item) for item in v]


class SkillStep(BaseModel):
    """最终技能输出步骤"""
    step_num: int = Field(..., ge=1)
    action: str = Field(..., min_length=1, max_length=1000)
    detail: str | None = None
    source_quote: str = Field(..., description="原文引用，防幻觉必填字段")
    source_chapter: str
    condition: str | None = None


class ModularSkill(BaseModel):
    """独立的专精技能定义 (Step 4: Skill Generator 产物)"""
    name: str = Field(..., description="技能名称, e.g. First_Principles_Analysis")
    description: str = Field(..., description="1-2句描述这个技能能做什么")
    when_to_use: list[str] = Field(..., description="触发该技能的具体场景或问题类型")
    thinking_steps: list[SkillStep] = Field(..., description="Agent 必须严格遵守的执行步骤")
    references_keywords: list[str] = Field(default_factory=list, description="用于离线 RAG 的检索关键词")

    @field_validator("when_to_use", "references_keywords", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, dict):
            return [str(val) for val in v.values()]
        if not isinstance(v, (list, tuple, set)):
            return [str(v)]
        return [str(item) for item in v]


class MasterRouter(BaseModel):
    """总调度入口 (Step 5: Router Generator 产物)"""
    agent_instruction: str = Field(..., description="顶级 Agent 的角色设定说明")
    routing_rules: dict[str, str] = Field(..., description="Map[场景描述, 对应应该调用的技能库名称]")

    @model_validator(mode="before")
    @classmethod
    def handle_hallucinations(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # 容错 0：检测 LLM 把 JSON Schema 定义本身当成输出返回的情况
        # 特征：包含 "properties" 或 "$defs" 字段，但没有 agent_instruction / routing_rules
        is_schema_itself = (
            ("properties" in data or "$defs" in data or "$schema" in data)
            and "agent_instruction" not in data
            and "routing_rules" not in data
        )
        if is_schema_itself:
            raise ValueError(
                "LLM returned the JSON Schema definition instead of actual data. "
                "Triggering retry via tenacity."
            )

        # 容错 1：大模型有时会将整个对象嵌套在一个字段里，如 {"MasterRouter": {...}} 或 {"data": {...}}
        if len(data) == 1:
            key = list(data.keys())[0]
            if isinstance(data[key], dict) and ("agent_instruction" in data[key] or "routing_rules" in data[key]):
                return data[key]

        # 容错 2：大模型可能使用了错误的字段名（比如把 description 当成了 key）
        # 如果缺少核心字段但存在类似含义的 key
        if "agent_instruction" not in data:
            for k, v in data.items():
                if any(x in k.lower() for x in ["instruction", "角色", "设定", "说明"]):
                    data["agent_instruction"] = v
                    break

        if "routing_rules" not in data:
            for k, v in data.items():
                if any(x in k.lower() for x in ["rule", "路由", "规则", "场景", "mapping"]):
                    data["routing_rules"] = v
                    break

        return data


# ─── Skill Package API Schemas ───────────────────────────────────────────────


class SkillPackageResponse(BaseModel):
    id: uuid.UUID
    book_id: uuid.UUID
    skill_md: str | None
    scripts: dict | None
    templates: dict | None
    zip_path: str | None = None
    version: int
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GenerateSkillRequest(BaseModel):
    focus_chapters: list[int] | None = None
    user_goal: str | None = None
    reuse_extracted_kus: bool = True


class GenerateCollectionSkillRequest(BaseModel):
    user_goal: str | None = None
    reuse_extracted_kus: bool = True
    detect_conflicts: bool = True


# ─── Chat / Refine Schemas ───────────────────────────────────────────────────

class RefineRequest(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=2000)

class MessageDict(BaseModel):
    role: str
    content: str

class PlaygroundRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[MessageDict] = Field(default_factory=list)


class QARequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


class QAResponse(BaseModel):
    answer: str
    sources: list[dict]


# ─── Pack / Download ─────────────────────────────────────────────────────────

class PackResponse(BaseModel):
    skill_package_id: uuid.UUID
    zip_path: str
    message: str = "skills.zip ready for download"
