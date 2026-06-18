"""
Celery 异步任务 — 处理书籍的完整 Pipeline
上传后在后台运行：解析 → 分块 → 嵌入 → 生成 references/
"""
import asyncio
import logging
import uuid
from pathlib import Path

from app.core.config import settings
from app.models.models import Book, Chapter
from app.pipeline.chunker import DocumentChunker
from app.pipeline.embedder import EmbeddingService
from app.pipeline.parser import DocumentParser
from app.pipeline.ref_generator import ReferenceGenerator
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def process_book_task(self, book_id: str, file_path: str):
    """
    书籍处理主任务（异步 Pipeline）:
    1. 解析文档
    2. 切分文本块
    3. 嵌入向量并存入 Qdrant
    4. 生成 references/ 目录
    5. 更新数据库状态
    """
    asyncio.run(_process_book_async(book_id, file_path))


async def _process_book_async(book_id: str, file_path: str):
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    # 在任务内部创建独立的引擎，避免在 Celery fork 进程间共享连接池
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    parser = DocumentParser()
    chunker = DocumentChunker()
    embedder = EmbeddingService()
    ref_gen = ReferenceGenerator()

    async with async_session() as db:
        # 1. 更新状态为 processing
        book = await db.get(Book, uuid.UUID(book_id))
        if not book:
            await engine.dispose()
            raise ValueError(f"Book {book_id} not found")

        book.status = "processing"
        await db.commit()

    # 重新开启 session 以避免长期持有事务
    async with async_session() as db:
        book = await db.get(Book, uuid.UUID(book_id))
        try:
            # 2. 解析文档 (耗时操作，不应持有数据库连接)
            parsed = parser.parse(file_path)

            # 更新书籍元数据
            book.title = parsed.title
            book.author = parsed.author
            book.page_count = parsed.page_count

            # 3. 保存章节到数据库
            for chapter in parsed.chapters:
                db_chapter = Chapter(
                    book_id=uuid.UUID(book_id),
                    title=chapter.title,
                    chapter_num=chapter.chapter_num,
                    page_start=chapter.page_start,
                    page_end=chapter.page_end,
                )
                db.add(db_chapter)
            await db.commit()

            # 4. 分块
            chunks = chunker.chunk_chapters(parsed.chapters, book_id)

            # 5. 嵌入向量
            await embedder.embed_chunks(chunks, book_id)

            # 6. 生成 references/ 目录
            storage_dir = Path(settings.STORAGE_LOCAL_PATH) / book_id
            storage_dir.mkdir(parents=True, exist_ok=True)
            ref_gen.generate(
                chapters=parsed.chapters,
                output_dir=str(storage_dir),
                book_title=parsed.title or "未知书名",
            )

            # 7. 标记完成
            book.status = "ready"
            await db.commit()

        except Exception as e:
            book.status = "error"
            book.error_message = str(e)
            await db.commit()
            raise
        finally:
            try:
                await embedder.aclose()
            except Exception as cleanup_error:
                logger.warning("EmbeddingService cleanup error (ignored): %s", cleanup_error)
            await engine.dispose()
