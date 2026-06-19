"""API 路由 — Collection Skill Package 管理"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.models.models import CollectionSkillPackage
from app.pipeline.packer import SkillPacker
from app.schemas.schemas import CollectionSkillPackageResponse, PackResponse, RetryCollectionSkillRequest
from app.api.routes.collections import (
    _ensure_collection_generateable,
    _get_collection_or_404,
    _is_retryable_collection_skill,
)
from app.tasks.generate_collection_skill import generate_collection_skill_task

router = APIRouter(prefix="/api/collection-skills", tags=["collection-skills"])


def _build_collection_skill_response(
    package: CollectionSkillPackage,
) -> CollectionSkillPackageResponse:
    return CollectionSkillPackageResponse(
        id=package.id,
        collection_id=package.collection_id,
        skill_md=package.skill_md,
        scripts=package.scripts,
        templates=package.templates,
        zip_path=package.zip_path,
        version=package.version,
        status=package.status,
        is_retryable=_is_retryable_collection_skill(package),
        created_at=package.created_at,
        updated_at=package.updated_at,
    )


def _ensure_packable_collection_skill(package: CollectionSkillPackage) -> None:
    if package.status != "ready":
        raise HTTPException(400, detail=f"Collection 技能包尚未就绪，当前状态：{package.status}")
    if not package.skill_md:
        raise HTTPException(400, detail="Collection 技能包缺少 SKILL.md，无法打包")


async def _get_collection_skill_or_404(
    skill_id: uuid.UUID,
    db: AsyncSession,
) -> CollectionSkillPackage:
    package = await db.get(
        CollectionSkillPackage,
        skill_id,
        options=[selectinload(CollectionSkillPackage.collection)],
    )
    if not package:
        raise HTTPException(404, detail="Collection 技能包不存在")
    return package


@router.get("/{skill_id}", response_model=CollectionSkillPackageResponse)
async def get_collection_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    package = await _get_collection_skill_or_404(skill_id, db)
    return _build_collection_skill_response(package)


@router.post("/{skill_id}/pack", response_model=PackResponse)
async def pack_collection_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    package = await _get_collection_skill_or_404(skill_id, db)
    _ensure_packable_collection_skill(package)

    storage_dir = Path(settings.STORAGE_LOCAL_PATH) / "collections" / str(package.collection_id)
    zip_path = storage_dir / f"skills_{skill_id}.zip"
    collection_name = package.collection.name if package.collection else "Collection Skill"

    packer = SkillPacker()
    zip_path_str = packer.pack(
        skill_md=package.skill_md or "",
        references_dir=str(storage_dir),
        scripts=package.scripts,
        templates=package.templates,
        output_path=str(zip_path),
        book_title=collection_name,
    )

    package.zip_path = zip_path_str
    await db.commit()

    return PackResponse(skill_package_id=skill_id, zip_path=zip_path_str)


@router.post("/{skill_id}/retry", response_model=CollectionSkillPackageResponse)
async def retry_collection_skill(
    skill_id: uuid.UUID,
    request: RetryCollectionSkillRequest,
    db: AsyncSession = Depends(get_db),
):
    package = await _get_collection_skill_or_404(skill_id, db)
    if not _is_retryable_collection_skill(package):
        raise HTTPException(400, detail=f"当前状态不可重试：{package.status}")

    collection = await _get_collection_or_404(package.collection_id, db)
    _ensure_collection_generateable(collection)

    new_package = CollectionSkillPackage(
        collection_id=package.collection_id,
        status="generating",
    )
    db.add(new_package)
    await db.commit()
    await db.refresh(new_package)

    generate_collection_skill_task.delay(
        skill_package_id=str(new_package.id),
        collection_id=str(package.collection_id),
        user_goal=request.user_goal,
        detect_conflicts=request.detect_conflicts,
    )

    return _build_collection_skill_response(new_package)


@router.get("/{skill_id}/download")
async def download_collection_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    package = await _get_collection_skill_or_404(skill_id, db)
    if not package.zip_path:
        raise HTTPException(404, detail="Collection 技能包 zip 文件不存在，请先执行打包")
    zip_path = Path(package.zip_path)
    if not zip_path.exists():
        raise HTTPException(404, detail="zip 文件已丢失，请重新打包")
    return FileResponse(
        path=str(zip_path),
        filename="skills.zip",
        media_type="application/zip",
    )
