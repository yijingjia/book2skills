"""
Celery 异步任务 — 技能包生成完整 Pipeline

将 `api/routes/skills.py` 中原有的 `_generate_skill_background` 整体迁移至此，
由 Celery 接管任务调度，获得：
  - 持久化任务队列（Redis），进程崩溃不丢任务
  - 自动重试（max_retries=2）
  - 与 process_book_task 统一的错误状态回写模式
"""
import asyncio
import json
import logging
import re
import uuid

from app.core.config import settings
from app.schemas.schemas import KnowledgeUnit
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _knowledge_units_to_store_items(kus: list[KnowledgeUnit]) -> list[dict]:
    return [{"ku": ku, "source_quote": None, "tags": []} for ku in kus]


@celery_app.task(bind=True, max_retries=2)
def generate_skill_task(
    self,
    skill_package_id: str,
    book_id: str,
    book_title: str,
    chapters: list[dict],
    focus_chapters: list[int] | None,
    user_goal: str | None,
    reuse_extracted_kus: bool = True,
):
    """
    技能包生成主任务 (Celery)
    """
    try:
        asyncio.run(
            _generate_skill_async(
                skill_package_id=skill_package_id,
                book_id=book_id,
                book_title=book_title,
                chapters=chapters,
                focus_chapters=focus_chapters,
                user_goal=user_goal,
                reuse_extracted_kus=reuse_extracted_kus,
            )
        )
    except Exception as exc:
        logger.error(
            f"generate_skill_task failed for package {skill_package_id}: {exc}",
            exc_info=True,
        )
        raise self.retry(exc=exc, countdown=30)


async def _generate_skill_async(
    skill_package_id: str,
    book_id: str,
    book_title: str,
    chapters: list[dict],
    focus_chapters: list[int] | None,
    user_goal: str | None,
    reuse_extracted_kus: bool = True,
) -> None:
    """后台异步执行技能包生成 pipeline"""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.llm import get_embedding_client
    from app.models.models import Skill, SkillPackage
    from app.pipeline.book_knowledge_unit_store import (
        load_book_knowledge_units_for_book_id,
        replace_book_knowledge_units,
    )
    from app.pipeline.cluster_generator import ClusterGenerator
    from app.pipeline.extractor import KnowledgeExtractor
    from app.pipeline.retriever import RAGRetriever
    from app.pipeline.router_generator import RouterGenerator
    from app.pipeline.skill_generator import SkillGenerator
    from app.schemas.schemas import ModularSkill

    # 在任务内部创建独立引擎
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    extractor = None
    cluster_gen = None
    skill_gen = None
    router_gen = None
    retriever = None
    embedder = None

    async with async_session() as db:
        kus = None
        current_phase = "init"
        try:
            skill = await db.get(SkillPackage, uuid.UUID(skill_package_id))
            if not skill:
                logger.error(f"SkillPackage {skill_package_id} not found in task")
                return

            extractor = KnowledgeExtractor()
            cluster_gen = ClusterGenerator()
            skill_gen = SkillGenerator()
            router_gen = RouterGenerator()
            retriever = RAGRetriever()

            # --- 检查是否可以复用 KUs ---
            kus_loaded_from_table = False
            if reuse_extracted_kus:
                existing_kus = await load_book_knowledge_units_for_book_id(db, uuid.UUID(book_id))
                if existing_kus:
                    kus = existing_kus
                    kus_loaded_from_table = True
                    logger.info(
                        "Loaded %d KUs from book_knowledge_units for book %s.",
                        len(kus),
                        book_id,
                    )

            if not kus:
                # --- Phase 1: 检索 Chunks ---
                current_phase = "phase1_retrieval"
                logger.info(f"Phase 1: Retrieving chunks for package {skill_package_id}")
                target_chapters = focus_chapters or [c["chapter_num"] for c in chapters]
                logger.info(f"Targeting chapters: {target_chapters}")

                # 通用方法论 query：指导 Qdrant 优先返回含方法/原理/步骤的高价值段落
                methodology_query = (
                    "方法论 原理 步骤 规律 框架 如何 策略 流程 模型 "
                    "methodology principle steps framework how-to strategy process model"
                )
                if user_goal:
                    methodology_query = f"{user_goal} {methodology_query}"

                # Embed 一次，并行检索所有章节（避免 N 次串行 embed API 调用）
                logger.info("Embedding methodology query (once for all chapters)...")
                query_vector = await retriever.embeddings.aembed_query(methodology_query)

                async def _fetch_chapter(chapter_num: int):
                    return await retriever.retrieve_by_chapter_vec(
                        book_id=book_id,
                        chapter_num=chapter_num,
                        query_vector=query_vector,
                        max_chunks=12,
                    )

                chapter_tasks = [_fetch_chapter(num) for num in target_chapters]
                chapter_results = await asyncio.gather(*chapter_tasks)
                all_chunks = [chunk for chapter_chunks in chapter_results for chunk in chapter_chunks]
                logger.info(f"Successfully retrieved {len(all_chunks)} total chunks from {len(target_chapters)} chapters (parallel).")

                # --- Phase 2: 提取 Knowledge Units ---
                current_phase = "phase2_extraction"
                logger.info(f"Phase 2: Extracting KUs from {len(all_chunks)} chunks...")
                kus = await extractor.extract_from_chunks(chunks=all_chunks, max_concurrency=10)
                logger.info(f"Phase 2 complete. Extracted {len(kus)} Knowledge Units.")

                if not kus:
                    raise ValueError(
                        "未提取到任何有价值的 Knowledge Unit，生成失败。"
                    )

            # 立即序列化 kus 备用，以防后续崩溃时可降级保存
            kus_json_str = json.dumps(
                [ku.model_dump() for ku in kus], ensure_ascii=False, indent=2
            )
            # Save checkpoint right after KU extraction/reuse so the next run can skip Phase 1/2.
            current_phase = "phase2_checkpoint_persist"
            skill.scripts = {
                **(skill.scripts or {}),
                "extracted_kus_partial.json": kus_json_str,
                "pipeline_phase": "phase2_completed",
            }
            await db.commit()
            if not kus_loaded_from_table:
                await replace_book_knowledge_units(
                    db=db,
                    book_id=uuid.UUID(book_id),
                    units=_knowledge_units_to_store_items(kus),
                    generated_by="llm",
                    generator_name=None,
                    skill_package_id=uuid.UUID(skill_package_id),
                )
                await db.commit()
            current_phase = "phase2_checkpointed"
            logger.info(
                "Phase 2 checkpoint persisted for package %s (KUs=%d).",
                skill_package_id,
                len(kus),
            )

            # --- Phase 2.5: 向量聚类 ---
            current_phase = "phase2_5_clustering"
            logger.info(f"Phase 2.5: Clustering {len(kus)} KUs via Vector Embeddings")
            clustered_groups = await cluster_gen.cluster_knowledge_units(kus)
            logger.info(f"Clustering complete. Found {len(clustered_groups)} skill modules.")

            # --- Phase 3: 并发生成 Modular Skills ---
            current_phase = "phase3_skill_generation"
            logger.info(f"Phase 3: Generating {len(clustered_groups)} Modular Skills...")
            skill_sem = asyncio.Semaphore(3)

            async def _bounded_skill(theme_name: str, group_kus: list) -> ModularSkill:
                async with skill_sem:
                    return await skill_gen.generate_modular_skill(
                        book_title=book_title,
                        knowledge_units=group_kus,
                        theme_hint=theme_name,
                    )

            async def _run_skill(theme_name: str, group_kus: list):
                try:
                    result = await _bounded_skill(theme_name, group_kus)
                    return theme_name, result
                except Exception as exc:
                    logger.warning(
                        "Phase 3: failed to generate skill for theme %s: %s",
                        theme_name,
                        exc,
                        exc_info=True,
                    )
                    return theme_name, exc

            skill_tasks = [
                _run_skill(theme_name, group_kus)
                for theme_name, _, group_kus in clustered_groups
            ]
            raw_results = await asyncio.gather(*skill_tasks)
            modular_skills: list[ModularSkill] = []
            failed_skills: list[dict[str, str]] = []
            for theme_name, result in raw_results:
                if isinstance(result, Exception):
                    failed_skills.append({
                        "theme": theme_name,
                        "error": str(result),
                    })
                else:
                    modular_skills.append(result)

            failed_count = len(failed_skills)
            if failed_count > 0:
                logger.warning(f"Phase 3: {failed_count} skill(s) failed and were skipped.")
            if not modular_skills:
                raise ValueError("所有 Skill 生成均失败，无可用技能模块。")
            logger.info(f"Phase 3 complete. Generated {len(modular_skills)} skills.")

            # 构建 markdown 和 scripts
            all_skills_md = []
            generation_report = {
                "status": "partial_success" if failed_count > 0 else "success",
                "total_modules": len(clustered_groups),
                "generated_modules": len(modular_skills),
                "failed_modules": failed_count,
                "failed_themes": failed_skills,
            }
            scripts_dict = {
                "extracted_kus.json": kus_json_str,
                "generation_report.json": json.dumps(
                    generation_report, ensure_ascii=False, indent=2
                ),
            }
            for i, ms in enumerate(modular_skills):
                md_content = skill_gen.render_skill_md(ms, book_title=book_title)
                all_skills_md.append(md_content)
                safe_name = re.sub(r'[^\w\-_.]', '_', ms.name).replace(' ', '_')
                scripts_dict[f"skill_{i}_{safe_name}.md"] = md_content

            # --- Phase 3.5: 落库 Postgres + Qdrant ---
            current_phase = "phase3_5_persist_vectors"
            logger.info("Phase 3.5: Injecting Skills into Database and Vector Store")
            qdrant = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY or None,
            )
            collection_name = "skills_vectors"
            if not qdrant.collection_exists(collection_name):
                qdrant.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=settings.EMBEDDING_DIMENSION, distance=Distance.COSINE
                    ),
                )

            embedder = get_embedding_client()
            qdrant_points = []

            for ms in modular_skills:
                skill_id = uuid.uuid4()
                db_skill = Skill(
                    id=skill_id,
                    book_id=uuid.UUID(book_id),
                    skill_package_id=uuid.UUID(skill_package_id),
                    name=ms.name,
                    description=ms.description,
                    when_to_use=ms.when_to_use,
                    workflow=[s.model_dump() for s in ms.thinking_steps],
                    templates={},
                )
                db.add(db_skill)

                workflow_text = "; ".join(
                    [f"Step {s.step_num}: {s.action}" for s in ms.thinking_steps]
                )
                when_to_use_text = ", ".join(ms.when_to_use)
                embedding_text = (
                    f"技能名: {ms.name}\n"
                    f"适用场景: {when_to_use_text}\n"
                    f"操作步骤: {workflow_text}"
                )
                vector = await embedder.aembed_query(embedding_text)
                qdrant_points.append(
                    PointStruct(
                        id=str(skill_id),
                        vector=vector,
                        payload={
                            "book_id": book_id,
                            "skill_package_id": skill_package_id,
                            "name": ms.name,
                            "description": ms.description,
                        },
                    )
                )

            # 先 commit Postgres，再 upsert Qdrant（避免向量孤立写入）
            await db.commit()
            logger.info(f"Postgres: committed {len(modular_skills)} skills.")

            if qdrant_points:
                qdrant.upsert(collection_name=collection_name, points=qdrant_points)
                logger.info(f"Qdrant: upserted {len(qdrant_points)} skill vectors.")

            # --- Phase 4: Master Router ---
            current_phase = "phase4_router_generation"
            logger.info("Phase 4: Generating Master Router")
            router = await router_gen.generate_master_router(
                book_title=book_title,
                skills=modular_skills,
            )
            if router is None:
                raise ValueError("MasterRouter 生成失败（3 次重试已耗尽）。")
            router_md = router_gen.render_router_md(router, book_title=book_title)

            final_content = f"{router_md}\n\n"
            for md in all_skills_md:
                final_content += f"---\n\n{md}\n\n"

            skill.skill_md = final_content
            skill.scripts = {
                **scripts_dict,
                "pipeline_phase": "completed",
            }
            skill.templates = None
            skill.status = "ready"
            logger.info(f"Pipeline complete. Package {skill_package_id} is ready.")

        except Exception as e:
            logger.error(
                f"Error generating skill package {skill_package_id}: {e}", exc_info=True
            )
            skill.status = "error"
            existing_scripts = skill.scripts or {}
            skill.scripts = {
                **existing_scripts,
                "pipeline_phase": f"failed_at_{current_phase}",
                "failed_reason": str(e),
            }

            # 尽最大努力保存已提取的中间 KU 资产
            if kus:
                try:
                    fallback_json = json.dumps(
                        [ku.model_dump() for ku in kus], ensure_ascii=False, indent=2
                    )
                    skill.scripts = {
                        **(skill.scripts or {}),
                        "extracted_kus_partial.json": fallback_json,
                    }
                    skill.skill_md = (
                        f"# ⚠️ 生成中断报告\n\n"
                        f"在生成此技能包的后续分类阶段遭遇系统级崩溃：`{str(e)}`。\n\n"
                        f"**但好消息是**：系统在崩溃前已经成功从本书提取出了 {len(kus)} 条"
                        f"高质量的基础法则 (Knowledge Units)。\n\n"
                        f"它们被保存在了本技能包的 `scripts/extracted_kus_partial.json` "
                        f"隐藏文件中（可随打包下载查阅），这些心血并未白费。"
                    )
                except Exception as inner_e:
                    logger.error(f"Failed to save partial KUs: {inner_e}")

        finally:
            for component in (extractor, cluster_gen, skill_gen, router_gen, retriever):
                if component is None:
                    continue
                close = getattr(component, "aclose", None)
                if close is not None:
                    try:
                        await close()
                    except Exception as _e:
                        logger.warning("Component cleanup error (ignored): %s", _e)
            if embedder is not None:
                try:
                    from app.core.llm import close_embedding_client
                    await close_embedding_client(embedder)
                except Exception as _e:
                    logger.warning("Embedding client cleanup error (ignored): %s", _e)
            try:
                await db.commit()
            finally:
                await engine.dispose()
