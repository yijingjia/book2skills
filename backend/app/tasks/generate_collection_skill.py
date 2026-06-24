"""Celery 异步任务 — Collection 综合技能包生成 Pipeline"""
import asyncio
import json
import logging
import re
import uuid
from datetime import UTC, datetime

from app.core.config import settings
from app.core.llm import get_chat_model, get_generation_model
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _build_model_config() -> dict:
    if settings.EMBEDDING_PROVIDER == "qwen":
        embedding_model = settings.QWEN_EMBEDDING_MODEL
    else:
        embedding_model = settings.OPENAI_EMBEDDING_MODEL

    return {
        "llm_provider": settings.LLM_PROVIDER,
        "generation_model": get_generation_model(),
        "chat_model": get_chat_model(),
        "embedding_provider": settings.EMBEDDING_PROVIDER,
        "embedding_model": embedding_model,
        "embedding_dimension": settings.EMBEDDING_DIMENSION,
    }


def _render_collection_skill_report(
    collection_name: str,
    source_books: list[dict],
    consensus: list[dict],
    candidate_tensions: list[dict],
) -> str:
    lines = [
        f"# {collection_name} 综合 Skill 生成报告",
        "",
        "## 来源书籍",
    ]
    for book in source_books:
        lines.append(f"- {book.get('title') or '未知书名'}")
    lines.append("")
    lines.append("## 跨书共识")
    for item in consensus:
        lines.append(f"- {item['theme']}：{item['supporting_book_count']} 本书支持，confidence={item['confidence']}")
    if candidate_tensions:
        lines.append("")
        lines.append("## 候选分歧与方法变体")
        lines.append("> 以下内容仅表示同一主题下存在不同命名或方法变体，不等同于已确认冲突。")
        for item in candidate_tensions:
            lines.append(f"- {item['theme']}：{', '.join(item.get('variants', []))}")
    return "\n".join(lines)


def _checkpoint_scripts(
    existing: dict | None,
    phase: str,
    artifacts: dict[str, str],
) -> dict:
    return {
        **(existing or {}),
        **artifacts,
        "pipeline_phase": phase,
    }


@celery_app.task(bind=True, max_retries=2)
def generate_collection_skill_task(
    self,
    skill_package_id: str,
    collection_id: str,
    user_goal: str | None,
    detect_conflicts: bool = True,
):
    try:
        asyncio.run(
            _generate_collection_skill_async(
                skill_package_id=skill_package_id,
                collection_id=collection_id,
                user_goal=user_goal,
                detect_conflicts=detect_conflicts,
            )
        )
    except Exception as exc:
        logger.error("generate_collection_skill_task failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=30)


async def _generate_collection_skill_async(
    skill_package_id: str,
    collection_id: str,
    user_goal: str | None,
    detect_conflicts: bool,
) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.llm import close_embedding_client, get_embedding_client
    from app.models.models import CollectionSkillPackage
    from app.pipeline.cluster_generator import ClusterGenerator
    from app.pipeline.collection_ku_loader import load_book_kus, load_collection_with_books
    from app.pipeline.collection_synthesis import (
        build_candidate_tension_artifacts,
        build_consensus_artifacts,
    )
    from app.pipeline.cross_book_normalizer import normalize_cross_book_kus
    from app.pipeline.ku_same_as_judge import KUSameAsJudge
    from app.pipeline.router_generator import RouterGenerator
    from app.pipeline.skill_generator import SkillGenerator
    from app.schemas.schemas import ModularSkill

    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    cluster_gen = None
    skill_gen = None
    router_gen = None
    embedder = None
    package = None

    async with async_session() as db:
        current_phase = "init"
        try:
            package = await db.get(CollectionSkillPackage, uuid.UUID(skill_package_id))
            if not package:
                logger.error("CollectionSkillPackage %s not found", skill_package_id)
                return
            package.scripts = _checkpoint_scripts(
                package.scripts,
                "started",
                {
                    "started_at": _utc_now_iso(),
                    "model_config.json": _json(_build_model_config()),
                },
            )
            await db.commit()

            # Step 1-3: load collection + books
            current_phase = "loading_collection"
            collection = await load_collection_with_books(db, uuid.UUID(collection_id))
            memberships = sorted(collection.books or [], key=lambda m: m.order_index)
            books = [m.book for m in memberships if m.book is not None]
            if len(books) < 2:
                raise ValueError("综合 skill 至少需要两本书")

            # Step 4-5: load KUs per book
            current_phase = "loading_kus"
            all_source_kus = []
            for book in books:
                book_kus = await load_book_kus(db, book)
                all_source_kus.extend(book_kus)

            source_books_meta = [
                {"book_id": str(book.id), "title": book.title, "author": book.author}
                for book in books
            ]

            # Step 6: checkpoint source_kus_loaded
            current_phase = "source_kus_loaded"
            package.scripts = _checkpoint_scripts(
                package.scripts,
                "source_kus_loaded",
                {
                    "source_books.json": _json(source_books_meta),
                    "source_kus.json": _json([ku.model_dump() for ku in all_source_kus]),
                },
            )
            await db.commit()

            # Step 7: non-destructive normalization
            current_phase = "normalizing_kus"
            embedder = get_embedding_client()
            normalization = await normalize_cross_book_kus(
                all_source_kus,
                embedder,
                top_k=settings.COLLECTION_NORMALIZATION_TOP_K,
                min_similarity=settings.COLLECTION_NORMALIZATION_MIN_SIMILARITY,
                judge=KUSameAsJudge(batch_size=settings.COLLECTION_SAME_AS_JUDGE_BATCH_SIZE),
            )
            deduped_kus = normalization.deduped_view_kus

            # Step 8: checkpoint normalized_kus_ready
            current_phase = "normalized_kus_ready"
            package.scripts = _checkpoint_scripts(
                package.scripts,
                "normalized_kus_ready",
                {
                    "ku_similarity_candidates.json": _json(normalization.similarity_candidates),
                    "same_as_judgments.json": _json(normalization.same_as_judgments),
                    "normalized_ku_groups.json": _json(normalization.normalized_ku_groups),
                    "same_as_edges.json": _json(normalization.same_as_edges),
                    "deduped_view.json": _json(normalization.deduped_view),
                },
            )
            await db.commit()

            # Step 9: cluster (skip internal dedup — sources already preserved)
            current_phase = "clustering"
            cluster_gen = ClusterGenerator()
            clustered_groups = await cluster_gen.cluster_knowledge_units(deduped_kus, deduplicate=False)

            # Step 10: checkpoint themes_ready
            current_phase = "themes_ready"
            themes_data = [
                {"theme": name, "description": desc, "ku_count": len(kus)}
                for name, desc, kus in clustered_groups
            ]
            package.scripts = _checkpoint_scripts(
                package.scripts,
                "themes_ready",
                {"themes.json": _json(themes_data)},
            )
            await db.commit()

            # Step 11: consensus artifacts
            total_books = len(books)
            consensus = build_consensus_artifacts(clustered_groups, total_books)

            # Step 12: candidate tensions (only if detect_conflicts)
            if detect_conflicts:
                candidate_tensions = build_candidate_tension_artifacts(clustered_groups)
            else:
                candidate_tensions = []

            package.scripts = _checkpoint_scripts(
                package.scripts,
                "themes_ready",
                {
                    "consensus.json": _json(consensus),
                    "candidate_tensions.json": _json(candidate_tensions),
                },
            )
            await db.commit()

            # Step 13: generate modular skills
            current_phase = "skill_modules_ready"
            skill_gen = SkillGenerator()
            skill_sem = asyncio.Semaphore(3)

            async def _bounded_skill(theme_name: str, group_kus: list):
                async with skill_sem:
                    combined_hint = (
                        f"{theme_name}（用户目标：{user_goal}）" if user_goal else theme_name
                    )
                    return await skill_gen.generate_modular_skill(
                        book_title=collection.name,
                        knowledge_units=group_kus,
                        theme_hint=combined_hint,
                    )

            async def _run_skill(theme_name: str, group_kus: list):
                try:
                    result = await _bounded_skill(theme_name, group_kus)
                    return theme_name, result
                except Exception as exc:
                    logger.warning("Skill gen failed for theme %s: %s", theme_name, exc)
                    return theme_name, exc

            skill_tasks = [_run_skill(name, kus) for name, _, kus in clustered_groups]
            raw_results = await asyncio.gather(*skill_tasks)
            modular_skills: list[ModularSkill] = []
            for _theme, result in raw_results:
                if not isinstance(result, Exception):
                    modular_skills.append(result)

            if not modular_skills:
                raise ValueError("所有 Skill 生成均失败，无可用技能模块。")

            # Step 14: render skill_*.md
            scripts_dict = dict(package.scripts or {})
            all_skills_md = []
            for i, ms in enumerate(modular_skills):
                md_content = skill_gen.render_skill_md(ms, book_title=collection.name)
                all_skills_md.append(md_content)
                safe_name = re.sub(r"[^\w\-_.]", "_", ms.name).replace(" ", "_")
                scripts_dict[f"skill_{i}_{safe_name}.md"] = md_content

            generation_report = {
                "status": "success",
                "total_modules": len(clustered_groups),
                "generated_modules": len(modular_skills),
            }
            scripts_dict["generation_report.json"] = _json(generation_report)
            scripts_dict["pipeline_phase"] = "skill_modules_ready"
            package.scripts = scripts_dict
            await db.commit()

            # Step 15: router
            current_phase = "router_ready"
            router_gen = RouterGenerator()
            router = await router_gen.generate_master_router(
                book_title=collection.name,
                skills=modular_skills,
            )
            if router is None:
                raise ValueError("MasterRouter 生成失败（重试已耗尽）。")
            router_md = router_gen.render_router_md(router, book_title=collection.name)

            # Step 16: build report + save
            report_md = _render_collection_skill_report(
                collection_name=collection.name,
                source_books=source_books_meta,
                consensus=consensus,
                candidate_tensions=candidate_tensions,
            )
            final_content = f"{report_md}\n\n{router_md}\n\n"
            for md in all_skills_md:
                final_content += f"---\n\n{md}\n\n"

            package.skill_md = final_content
            package.scripts = {
                **scripts_dict,
                "pipeline_phase": "completed",
                "completed_at": _utc_now_iso(),
            }
            package.status = "ready"
            logger.info("Collection pipeline complete. Package %s is ready.", skill_package_id)

        except Exception as exc:
            logger.error("Error generating collection skill %s: %s", skill_package_id, exc, exc_info=True)
            if package is not None:
                package.status = "error"
                package.scripts = {
                    **(package.scripts or {}),
                    "pipeline_phase": f"failed_at_{current_phase}",
                    "failed_at": _utc_now_iso(),
                    "failed_reason": str(exc),
                }

        finally:
            for component in (cluster_gen, skill_gen, router_gen):
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
                    await close_embedding_client(embedder)
                except Exception as _e:
                    logger.warning("Embedding client cleanup error (ignored): %s", _e)
            try:
                await db.commit()
            finally:
                await engine.dispose()
