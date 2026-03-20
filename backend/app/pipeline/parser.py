"""
文档解析器 — 支持 PDF (PyMuPDF) 和 EPUB (ebooklib)
输出标准化的章节列表，供 chunker 分块使用
"""
import re
from dataclasses import dataclass
from pathlib import Path

import ebooklib
import fitz  # PyMuPDF
from bs4 import BeautifulSoup
from ebooklib import epub


@dataclass
class RawChapter:
    chapter_num: int
    title: str
    text: str
    page_start: int | None = None
    page_end: int | None = None


@dataclass
class ParsedBook:
    title: str | None
    author: str | None
    page_count: int | None
    chapters: list[RawChapter]
    file_type: str  # 'pdf' | 'epub'


class DocumentParser:
    """解析 PDF / EPUB 文件，提取章节结构和正文"""

    # 噪声过滤：跳过这些类型的内容
    NOISE_PATTERNS = [
        r"^(前言|序言|目录|版权|致谢|参考文献|索引|附录)",
        r"^(Preface|Contents|Index|Bibliography|Appendix)",
    ]

    def parse(self, file_path: str) -> ParsedBook:
        """自动识别文件类型并解析"""
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self._parse_pdf(file_path)
        elif suffix == ".epub":
            return self._parse_epub(file_path)
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

    def _parse_pdf(self, file_path: str) -> ParsedBook:
        doc = fitz.open(file_path)
        meta = doc.metadata

        # 提取目录（outline）
        toc = doc.get_toc()  # [(level, title, page), ...]
        chapters: list[RawChapter] = []

        if toc:
            # 有目录结构，按目录提取
            top_level = [(t, p) for lvl, t, p in toc if lvl == 1]
            for i, (title, page_start) in enumerate(top_level):
                if self._is_noise(title):
                    continue
                page_end = top_level[i + 1][1] - 1 if i + 1 < len(top_level) else doc.page_count
                text = self._extract_pdf_pages(doc, page_start - 1, page_end - 1)
                chapters.append(RawChapter(
                    chapter_num=len(chapters) + 1,
                    title=title.strip(),
                    text=text,
                    page_start=page_start,
                    page_end=page_end,
                ))
        else:
            # 无目录，整本书作为一章
            text = self._extract_pdf_pages(doc, 0, doc.page_count - 1)
            chapters.append(RawChapter(
                chapter_num=1,
                title="全文",
                text=text,
                page_start=1,
                page_end=doc.page_count,
            ))

        return ParsedBook(
            title=meta.get("title") or Path(file_path).stem,
            author=meta.get("author"),
            page_count=doc.page_count,
            chapters=chapters,
            file_type="pdf",
        )

    def _extract_pdf_pages(self, doc: fitz.Document, start: int, end: int) -> str:
        """提取指定页码范围的文本，过滤页眉页脚噪声"""
        texts = []
        for i in range(start, min(end + 1, doc.page_count)):
            page = doc[i]
            text = page.get_text("text")
            text = self._clean_page_text(text)
            if text:
                texts.append(text)
        return "\n\n".join(texts)

    def _clean_page_text(self, text: str) -> str:
        """清理页眉页脚、多余空白"""
        lines = text.split("\n")
        # 去掉过短的行（可能是页码、页眉）
        lines = [line for line in lines if len(line.strip()) > 10]
        return "\n".join(lines).strip()

    def _parse_epub(self, file_path: str) -> ParsedBook:
        book = epub.read_epub(file_path)

        title = book.get_metadata("DC", "title")
        title = title[0][0] if title else None
        author = book.get_metadata("DC", "creator")
        author = author[0][0] if author else None

        chapters: list[RawChapter] = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_content(), "html.parser")
            heading = soup.find(["h1", "h2"])
            chapter_title = heading.get_text(strip=True) if heading else item.get_name()

            if self._is_noise(chapter_title):
                continue

            text = soup.get_text(separator="\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text)
            if len(text) < 200:  # 跳过过短的章节（可能是封面页等）
                continue

            chapters.append(RawChapter(
                chapter_num=len(chapters) + 1,
                title=chapter_title,
                text=text,
            ))

        return ParsedBook(
            title=title,
            author=author,
            page_count=None,
            chapters=chapters,
            file_type="epub",
        )

    def _is_noise(self, title: str) -> bool:
        for pattern in self.NOISE_PATTERNS:
            if re.match(pattern, title.strip(), re.IGNORECASE):
                return True
        return False
