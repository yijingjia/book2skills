"""API 路由 — 技能包管理"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.models.models import Book, SkillPackage
from app.pipeline.packer import SkillPacker
from app.schemas.schemas import GenerateSkillRequest, PackResponse, SkillPackageResponse
from app.tasks.generate_skill import generate_skill_task

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.post("/books/{book_id}/generate", response_model=SkillPackageResponse)
async def generate_skill(
    book_id: uuid.UUID,
    request: GenerateSkillRequest,
    db: AsyncSession = Depends(get_db),
):
    """触发技能包生成（Celery 异步任务）"""
    result = await db.execute(
        select(Book).where(Book.id == book_id).options(selectinload(Book.chapters))
    )
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(404, detail="书籍不存在")
    if book.status != "ready":
        raise HTTPException(400, detail="书籍尚未处理完成")

    skill_package = SkillPackage(
        book_id=book_id,
        status="generating",
    )
    db.add(skill_package)
    await db.commit()
    await db.refresh(skill_package)

    chapters_data = [
        {"chapter_num": c.chapter_num, "title": c.title}
        for c in sorted(book.chapters, key=lambda x: x.chapter_num)
    ]

    generate_skill_task.delay(
        skill_package_id=str(skill_package.id),
        book_id=str(book_id),
        book_title=book.title or "未知",
        chapters=chapters_data,
        focus_chapters=request.focus_chapters,
        user_goal=request.user_goal,
        reuse_extracted_kus=request.reuse_extracted_kus,
    )

    return SkillPackageResponse(
        id=skill_package.id,
        book_id=book_id,
        skill_md=None,
        scripts=None,
        templates=None,
        version=skill_package.version,
        status="generating",
        created_at=skill_package.created_at,
        updated_at=skill_package.updated_at,
    )


@router.get("/{skill_id}", response_model=SkillPackageResponse)
async def get_skill(skill_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    skill = await db.get(SkillPackage, skill_id)
    if not skill:
        raise HTTPException(404, detail="技能包不存在")
    return SkillPackageResponse.model_validate(skill)


@router.post("/{skill_id}/pack", response_model=PackResponse)
async def pack_skill(skill_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """将技能包打包为 skills.zip"""
    skill = await db.get(SkillPackage, skill_id)
    if not skill:
        raise HTTPException(404, detail="技能包不存在")
    if skill.status != "ready":
        raise HTTPException(400, detail=f"技能包尚未就绪，当前状态：{skill.status}")

    storage_dir = Path(settings.STORAGE_LOCAL_PATH) / str(skill.book_id)
    zip_path = storage_dir / f"skills_{skill_id}.zip"

    packer = SkillPacker()

    book = await db.get(Book, skill.book_id)
    book_title = book.title if book else "未知书籍"

    zip_path_str = packer.pack(
        skill_md=skill.skill_md or "",
        references_dir=str(storage_dir),
        scripts=skill.scripts,
        templates=skill.templates,
        output_path=str(zip_path),
        book_title=book_title,
    )

    skill.zip_path = zip_path_str
    await db.commit()

    return PackResponse(skill_package_id=skill_id, zip_path=zip_path_str)


@router.get("/{skill_id}/download")
async def download_skill(skill_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """下载 skills.zip"""
    skill = await db.get(SkillPackage, skill_id)
    if not skill or not skill.zip_path:
        raise HTTPException(404, detail="技能包 zip 文件不存在，请先执行打包")
    zip_path = Path(skill.zip_path)
    if not zip_path.exists():
        raise HTTPException(404, detail="zip 文件已丢失，请重新打包")
    return FileResponse(
        path=str(zip_path),
        filename="skills.zip",
        media_type="application/zip",
    )
