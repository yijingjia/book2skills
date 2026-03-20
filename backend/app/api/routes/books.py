"""API 路由 — 书籍管理"""
import hashlib
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.models.models import Book
from app.schemas.schemas import (
    BookDetailResponse,
    BookListResponse,
    BookStatusResponse,
    BookUploadResponse,
    ChapterResponse,
)
from app.tasks.process_book import process_book_task

router = APIRouter(prefix="/api/books", tags=["books"])

ALLOWED_EXTENSIONS = {".pdf", ".epub"}


@router.get("", response_model=list[BookListResponse])
async def list_books(db: AsyncSession = Depends(get_db)):
    """返回所有书籍及其最新技能包"""
    result = await db.execute(
        select(Book)
        .options(selectinload(Book.skill_packages))
        .order_by(desc(Book.created_at))
    )
    books = result.scalars().all()

    items = []
    for book in books:
        # 取最新的技能包
        latest_skill = None
        if book.skill_packages:
            latest_skill = sorted(book.skill_packages, key=lambda s: s.created_at, reverse=True)[0]
        items.append(BookListResponse(
            book_id=book.id,
            title=book.title,
            author=book.author,
            status=book.status,
            page_count=book.page_count,
            created_at=book.created_at,
            skill_id=latest_skill.id if latest_skill else None,
            skill_status=latest_skill.status if latest_skill else None,
        ))
    return items


@router.post("/upload", response_model=BookUploadResponse)
async def upload_book(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """上传 PDF / EPUB 文件，支持去重"""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, detail=f"不支持的文件格式：{suffix}")

    # 1. 计算文件哈希
    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()
    await file.seek(0)  # 重置文件指针供后续读取

    # 2. 检查去重
    result = await db.execute(
        select(Book).where(Book.file_hash == file_hash)
    )
    existing_book = result.scalar_one_or_none()
    if existing_book:
        # 如果书籍已存在但处于错误或挂起状态，重试处理
        if existing_book.status in ["pending", "error"]:
            existing_book.status = "pending"
            existing_book.error_message = None
            await db.commit()
            process_book_task.delay(str(existing_book.id), existing_book.file_path)
            return BookUploadResponse(
                book_id=existing_book.id,
                message="书籍处理曾失败或挂起，已重新开始处理",
                is_duplicate=True
            )

        return BookUploadResponse(
            book_id=existing_book.id,
            message="书籍已存在，已跳转至处理结果",
            is_duplicate=True
        )

    if file.size and file.size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, detail=f"文件过大，最大支持 {settings.MAX_FILE_SIZE_MB}MB")

    book_id = uuid.uuid4()
    storage_dir = Path(settings.STORAGE_LOCAL_PATH) / str(book_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"original{suffix}"

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    book = Book(
        id=book_id,
        file_path=str(file_path),
        file_type=suffix.lstrip("."),
        status="pending",
        file_hash=file_hash,
    )
    db.add(book)
    await db.commit()

    # 触发异步处理任务
    process_book_task.delay(str(book_id), str(file_path))

    return BookUploadResponse(book_id=book_id)


@router.get("/{book_id}/status", response_model=BookStatusResponse)
async def get_book_status(book_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(404, detail="书籍不存在")
    return BookStatusResponse(
        book_id=book.id,
        status=book.status,
        title=book.title,
        author=book.author,
        page_count=book.page_count,
        error_message=book.error_message,
        created_at=book.created_at,
    )


@router.get("/{book_id}/chapters", response_model=BookDetailResponse)
async def get_book_chapters(book_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Book).where(Book.id == book_id).options(selectinload(Book.chapters))
    )
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(404, detail="书籍不存在")
    if book.status != "ready":
        raise HTTPException(400, detail=f"书籍尚未处理完成，当前状态：{book.status}")

    return BookDetailResponse(
        book_id=book.id,
        title=book.title,
        author=book.author,
        status=book.status,
        chapters=[
            ChapterResponse(
                id=c.id,
                chapter_num=c.chapter_num,
                title=c.title,
                page_start=c.page_start,
                page_end=c.page_end,
            )
            for c in sorted(book.chapters, key=lambda x: x.chapter_num)
        ],
    )
