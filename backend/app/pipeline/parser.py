"""
文档解析器 — 支持 PDF (PyMuPDF) 和 EPUB (ebooklib)
输出标准化的章节列表，供 chunker 分块使用
"""
import re
from dataclasses import dataclass
from pathlib import Path

import ebooklib
import fitz  # PyMuPDF
import pymupdf4llm
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

    # 章节边界：独立的"第N章"行（中文数字或阿拉伯数字），兼容 `## 第N章`
    CHAPTER_MARKER_RE = re.compile(r"^(?:#{1,6}\s*)?第[一二三四五六七八九十百\d]+章\s*$")

    PREFACE_PATTERNS = [
        r"^#+\s*(PREFACE\s|再版序|初版序|序言)",
        r"^(PREFACE\s.*|再版序|初版序)\s*$",
    ]

    AFTERWORD_PATTERNS = [
        r"^#+\s*后记",
        r"^后记\s*$",
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
        page_count = doc.page_count
        doc.close()

        markdown = pymupdf4llm.to_markdown(file_path)
        chapters = self._split_markdown_into_chapters(markdown)

        if not chapters:
            chapters = [RawChapter(
                chapter_num=1,
                title="全文",
                text=markdown,
            )]

        self._build_page_index(file_path, chapters, page_count)

        return ParsedBook(
            title=meta.get("title") or Path(file_path).stem,
            author=meta.get("author"),
            page_count=page_count,
            chapters=chapters,
            file_type="pdf",
        )

    def _build_page_index(
        self,
        file_path: str,
        chapters: list[RawChapter],
        page_count: int | None = None,
    ) -> None:
        """Best-effort: set page_start/page_end on chapters by matching titles in page chunks.

        Matches titles as Markdown heading lines or standalone lines to avoid false
        positives from TOC pages, where titles appear mid-line with page-number dots.
        """
        try:
            page_chunks = pymupdf4llm.to_markdown(file_path, page_chunks=True)
        except Exception:
            return

        # Precompile per-chapter patterns: heading line OR standalone plain-text line.
        # This filters out TOC entries like "第1章 标题 .......... 7" which are never
        # on their own line, while still matching both `## 标题` and bare `后记` lines.
        title_patterns = {
            ch.title: re.compile(
                rf"^#{{1,3}}\s+{re.escape(ch.title)}\s*$|^{re.escape(ch.title)}\s*$",
                re.MULTILINE,
            )
            for ch in chapters
        }

        title_to_page: dict[str, int] = {}
        for chunk in page_chunks:
            metadata = chunk.get("metadata") or {}
            page_num = metadata.get("page") or metadata.get("page_number")
            if page_num is None:
                continue
            text = chunk.get("text", "")
            for ch in chapters:
                if title_patterns[ch.title].search(text) and ch.title not in title_to_page:
                    title_to_page[ch.title] = page_num

        sorted_pages = sorted(title_to_page.values())

        for ch in chapters:
            page = title_to_page.get(ch.title)
            if page is not None:
                ch.page_start = page
                later = [p for p in sorted_pages if p > page]
                ch.page_end = later[0] - 1 if later else page_count

    def _split_markdown_into_chapters(self, markdown: str) -> list[RawChapter]:
        """Split pymupdf4llm Markdown into chapters using '第N章' markers as boundaries.

        Heading level (# vs ##) is NOT used as a chapter boundary — only the
        standalone '第N章' line is. The first heading after a marker becomes the
        chapter title. Preface/afterword segments are detected separately.
        """
        lines = markdown.split("\n")

        # --- Pass 1: find chapter-marker line indices ---
        marker_indices: list[int] = []
        for i, line in enumerate(lines):
            if self.CHAPTER_MARKER_RE.match(line.strip()):
                marker_indices.append(i)

        # --- Pass 2: find preface/afterword start indices ---
        special_indices: list[tuple[int, str]] = []  # (line_index, detected_title)
        for i, line in enumerate(lines):
            stripped = line.strip()
            for pat in self.PREFACE_PATTERNS:
                if re.match(pat, stripped, re.IGNORECASE):
                    title = re.sub(r"^#+\s*", "", stripped).strip()
                    special_indices.append((i, title))
                    break
            for pat in self.AFTERWORD_PATTERNS:
                if re.match(pat, stripped, re.IGNORECASE):
                    title = re.sub(r"^#+\s*", "", stripped).strip()
                    special_indices.append((i, title))
                    break

        # --- Pass 3: merge and sort all boundary indices ---
        boundaries: list[tuple[int, str | None]] = []
        for idx in marker_indices:
            boundaries.append((idx, None))  # title resolved in pass 4
        for idx, title in special_indices:
            boundaries.append((idx, title))
        boundaries.sort(key=lambda x: x[0])

        if not boundaries:
            return []

        # --- Pass 4: extract segments ---
        chapters: list[RawChapter] = []
        for b_pos, (start_idx, preset_title) in enumerate(boundaries):
            end_idx = boundaries[b_pos + 1][0] if b_pos + 1 < len(boundaries) else len(lines)
            segment_lines = lines[start_idx:end_idx]

            # Resolve title: preset (preface/afterword) or first heading after marker.
            # Preset titles are always kept — _is_noise only applies to titles resolved
            # heuristically, since NOISE_PATTERNS includes "Preface" which would otherwise
            # strip out the very preface segments PREFACE_PATTERNS deliberately detects.
            title = preset_title
            body_start = 1  # skip the marker/heading line itself
            if title is None:
                for j, sl in enumerate(segment_lines[1:], start=1):
                    stripped = sl.strip()
                    if not stripped:
                        continue
                    heading_match = re.match(r"^#{1,6}\s+(.+)", stripped)
                    title = heading_match.group(1).strip() if heading_match else stripped
                    body_start = j + 1
                    break
                if title is None:
                    title = re.sub(r"^#+\s*", "", segment_lines[0].strip()).strip()

                if self._is_noise(title):
                    continue

            text = "\n".join(segment_lines[body_start:]).strip()
            if len(text) < 100:
                continue

            chapters.append(RawChapter(
                chapter_num=len(chapters) + 1,
                title=title,
                text=text,
            ))

        return chapters

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
