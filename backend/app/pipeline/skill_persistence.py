import asyncio
import logging
import re
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.llm import close_embedding_client, get_embedding_client
from app.models.models import Skill, SkillPackage
from app.schemas.schemas import AgentSkillMetadata, ModularSkill

logger = logging.getLogger(__name__)


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w\-_.]", "_", name).replace(" ", "_")


def render_modular_skill_markdown(skill: ModularSkill) -> str:
    lines = [
        f"# {skill.name}",
        "",
        "## 技能描述 (Description)",
        skill.description,
        "",
        "## 适用场景 (When to Use)",
    ]
    for item in skill.when_to_use:
        lines.append(f"- {item}")
    lines.extend(["", "## 核心思维步骤 (Thinking Steps)", ""])
    for step in skill.thinking_steps:
        lines.append(f"### Step {step.step_num}: {step.action}")
        if step.condition:
            lines.append(f"- 条件：{step.condition}")
        lines.append(f"- 原文引用：{step.source_quote}")
        lines.append(f"- 来源章节：{step.source_chapter}")
        lines.append("")
    if skill.references_keywords:
        lines.append("## 原文依据与溯源 (References)")
        for keyword in skill.references_keywords:
            lines.append(f"- {keyword}")
    return "\n".join(lines).strip() + "\n"


def build_agent_skill_markdown(router_md: str, skills: list[ModularSkill]) -> str:
    modules = [render_modular_skill_markdown(skill) for skill in skills]
    content = f"{router_md.strip()}\n\n"
    for module in modules:
        content += f"---\n\n{module}\n\n"
    return content


def build_agent_skill_scripts(
    router_md: str,
    skills: list[ModularSkill],
    extra_scripts: dict,
    metadata: AgentSkillMetadata,
) -> dict:
    scripts = dict(extra_scripts or {})
    scripts["router.md"] = router_md
    scripts["metadata"] = {
        "generated_by": metadata.generated_by,
        "agent_name": metadata.agent_name,
        "vector_index_status": "pending",
    }
    scripts["agent_ingest_report.json"] = {
        "status": "success",
        "generated_modules": len(skills),
    }
    for index, skill in enumerate(skills):
        scripts[f"skill_{index}_{_safe_name(skill.name)}.md"] = render_modular_skill_markdown(skill)
    return scripts


def build_skill_embedding_text(skill: ModularSkill) -> str:
    workflow_text = "; ".join(
        [f"Step {step.step_num}: {step.action}" for step in skill.thinking_steps]
    )
    when_to_use_text = ", ".join(skill.when_to_use)
    return (
        f"技能名: {skill.name}\n"
        f"适用场景: {when_to_use_text}\n"
        f"操作步骤: {workflow_text}"
    )


def build_skill_vector_payload(
    book_id: uuid.UUID,
    skill_package_id: uuid.UUID,
    skill_id: uuid.UUID,
    skill: ModularSkill,
) -> dict:
    return {
        "book_id": str(book_id),
        "skill_package_id": str(skill_package_id),
        "skill_id": str(skill_id),
        "name": skill.name,
        "description": skill.description,
        "generated_by": "agent",
    }


def build_skill_model_kwargs(
    skill_id: uuid.UUID,
    book_id: uuid.UUID,
    skill_package_id: uuid.UUID,
    skill: ModularSkill,
) -> dict:
    return {
        "id": skill_id,
        "book_id": book_id,
        "skill_package_id": skill_package_id,
        "name": skill.name,
        "description": skill.description,
        "when_to_use": skill.when_to_use,
        "workflow": [step.model_dump() for step in skill.thinking_steps],
        "templates": {},
    }


def _with_vector_index_status(
    scripts: dict | None,
    status: str,
    error: str | None = None,
) -> dict:
    updated = dict(scripts or {})
    metadata = dict(updated.get("metadata") or {})
    metadata["vector_index_status"] = status
    if error:
        metadata["vector_index_error"] = error[:500]
    else:
        metadata.pop("vector_index_error", None)
    updated["metadata"] = metadata
    return updated


def ensure_skills_vector_collection(qdrant: QdrantClient) -> None:
    collection_name = "skills_vectors"
    if not qdrant.collection_exists(collection_name):
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=settings.EMBEDDING_DIMENSION,
                distance=Distance.COSINE,
            ),
        )


async def _upsert_skill_vectors(qdrant: QdrantClient, points: list[PointStruct]) -> None:
    if not points:
        return
    await asyncio.to_thread(ensure_skills_vector_collection, qdrant)
    await asyncio.to_thread(qdrant.upsert, collection_name="skills_vectors", points=points)


async def persist_agent_skill_package(
    db: AsyncSession,
    book_id: uuid.UUID,
    router_md: str,
    skills: list[ModularSkill],
    scripts: dict,
    templates: dict | None,
    metadata: AgentSkillMetadata,
) -> SkillPackage:
    embedder = get_embedding_client()
    try:
        skill_ids = [uuid.uuid4() for _ in skills]
        embedding_texts = [build_skill_embedding_text(skill) for skill in skills]
        vectors = await embedder.aembed_documents(embedding_texts)
    finally:
        await close_embedding_client(embedder)

    base_scripts = build_agent_skill_scripts(router_md, skills, scripts, metadata)
    skill_package = SkillPackage(
        book_id=book_id,
        skill_md=build_agent_skill_markdown(router_md, skills),
        scripts=base_scripts,
        templates=templates,
        status="ready",
    )
    qdrant_points = []

    try:
        db.add(skill_package)
        await db.flush()

        for skill_id, skill, vector in zip(skill_ids, skills, vectors, strict=True):
            db.add(Skill(**build_skill_model_kwargs(skill_id, book_id, skill_package.id, skill)))
            qdrant_points.append(
                PointStruct(
                    id=str(skill_id),
                    vector=vector,
                    payload=build_skill_vector_payload(
                        book_id,
                        skill_package.id,
                        skill_id,
                        skill,
                    ),
                )
            )
        await db.commit()
        await db.refresh(skill_package)
    except Exception:
        await db.rollback()
        raise

    qdrant = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
    try:
        await _upsert_skill_vectors(qdrant, qdrant_points)
        skill_package.scripts = _with_vector_index_status(skill_package.scripts, "indexed")
    except Exception as exc:
        logger.exception("Agent skill package persisted but vector indexing failed")
        skill_package.scripts = _with_vector_index_status(skill_package.scripts, "error", str(exc))
    await db.commit()
    await db.refresh(skill_package)
    return skill_package
