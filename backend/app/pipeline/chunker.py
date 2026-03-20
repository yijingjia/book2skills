"""
文本分块器 — 将章节文本切分为适合 RAG 的语义块
同时生成 references/ 目录结构
"""
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.pipeline.parser import RawChapter


@dataclass
class TextChunk:
    chunk_index: int
    book_id: str
    chapter_num: int
    chapter_title: str
    text: str
    page_start: int | None
    page_end: int | None
    char_start: int
    char_end: int


class DocumentChunker:
    """将章节文本切分为带元数据的语义块"""

    def __init__(
        self,
        chunk_size: int = settings.CHUNK_SIZE,
        chunk_overlap: int = settings.CHUNK_OVERLAP,
    ):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " "],
        )

    def chunk_chapters(
        self,
        chapters: list[RawChapter],
        book_id: str,
    ) -> list[TextChunk]:
        """将所有章节切分为 TextChunk 列表"""
        all_chunks: list[TextChunk] = []
        global_index = 0

        for chapter in chapters:
            raw_chunks = self.splitter.split_text(chapter.text)
            char_pos = 0

            for raw_text in raw_chunks:
                if not raw_text.strip():
                    continue

                char_start = chapter.text.find(raw_text, char_pos)
                char_end = char_start + len(raw_text)
                char_pos = char_end

                all_chunks.append(TextChunk(
                    chunk_index=global_index,
                    book_id=book_id,
                    chapter_num=chapter.chapter_num,
                    chapter_title=chapter.title,
                    text=raw_text,
                    page_start=chapter.page_start,
                    page_end=chapter.page_end,
                    char_start=char_start,
                    char_end=char_end,
                ))
                global_index += 1

        return all_chunks

    def get_chapter_chunks(
        self,
        chunks: list[TextChunk],
        chapter_num: int,
    ) -> list[TextChunk]:
        """获取指定章节的所有块"""
        return [c for c in chunks if c.chapter_num == chapter_num]
