"""
文档解析器 — 支持 PDF (PyMuPDF) 和 EPUB (ebooklib)
输出标准化的章节列表，供 chunker 分块使用
"""
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import ebooklib
import fitz  # PyMuPDF
import pymupdf4llm
from bs4 import BeautifulSoup
from ebooklib import epub

logger = logging.getLogger(__name__)


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


@dataclass
class ChapterBoundary:
    line_index: int
    body_start_line: int
    kind: str  # "preface" | "chapter" | "afterword"
    marker: str
    chapter_number: int | None
    title: str


@dataclass
class ChapterBoundaryCandidate:
    line_index: int
    body_start_line: int
    kind: str  # "chapter" | "preface" | "afterword"
    marker: str
    chapter_number: int | None
    title: str
    score: int


class DocumentParser:
    """解析 PDF / EPUB 文件，提取章节结构和正文"""

    # 噪声过滤：跳过这些类型的内容
    NOISE_PATTERNS = [
        r"^(前言|序言|目录|版权|致谢|参考文献|索引|附录)",
        r"^(Preface|Contents|Index|Bibliography|Appendix)",
    ]

    CHINESE_NUMERAL_MAP = {
        "零": 0,
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }

    CHINESE_CHAPTER_RE = re.compile(
        r"^(?:#{1,6}\s*)?第\s*(?P<num>[一二三四五六七八九十百\d]+)\s*章(?:\s+(?P<title>.+))?\s*$"
    )
    ENGLISH_CHAPTER_RE = re.compile(
        r"^(?:#{1,6}\s*)?CHAPTER\s+(?P<num>\d+)(?:\s+(?P<title>.+))?\s*$",
        re.IGNORECASE,
    )
    TOC_LIKE_CHAPTER_RE = re.compile(
        r"^(?:#{1,6}\s*)?第\s*[一二三四五六七八九十百\d]+\s*章\s+\S+.*(?:\.{3,}|…{2,})\s*\d*\s*$"
    )
    # Matches English TOC entries like "CHAPTER 1 Foundations ........ 7"
    ENGLISH_TOC_LIKE_CHAPTER_RE = re.compile(
        r"^(?:#{1,6}\s*)?CHAPTER\s+\d+(?:\s+\S+.*)?(?:\.{3,}|…{2,})\s*\d*\s*$",
        re.IGNORECASE,
    )
    INLINE_CHINESE_CHAPTER_RE = re.compile(
        r"(?:^|[\s　])(?P<marker>第\s*(?P<num>[一二三四五六七八九十百\d]+)\s*章)\s*(?P<title>.+)$"
    )
    SECTION_TITLE_CUTOFF_RE = re.compile(
        r"\s+第[一二三四五六七八九十百\d]+\s*节(?:\s+|$)"
    )
    PREFACE_PATTERNS = [
        r"^#+\s*(PREFACE\s|再版序|初版序|序言|自序|前言)",
        r"^(PREFACE\s.*|再版序.*|初版序.*|序言.*|自序.*|前言.*)\s*$",
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

        for i, ch in enumerate(chapters):
            page = title_to_page.get(ch.title)
            if page is None:
                continue
            ch.page_start = page
            if i + 1 >= len(chapters):
                ch.page_end = page_count
            else:
                next_page = title_to_page.get(chapters[i + 1].title)
                if next_page is not None:
                    ch.page_end = next_page - 1

    def _clean_heading_marker(self, line: str) -> str:
        return re.sub(r"^#{1,6}\s*", "", line.strip()).strip()

    def _strip_section_suffix(self, title: str) -> str:
        section_match = self.SECTION_TITLE_CUTOFF_RE.search(title)
        if section_match:
            title = title[:section_match.start()]
        return title.strip()

    def _extract_inline_chapter_title(self, cleaned_line: str, marker: str) -> str:
        after_marker = cleaned_line.split(marker, 1)[1].strip()
        return self._strip_section_suffix(after_marker)

    def _is_toc_like_boundary_line(self, stripped: str) -> bool:
        cleaned = self._clean_heading_marker(stripped)
        if self.TOC_LIKE_CHAPTER_RE.match(stripped):
            return True
        if self.ENGLISH_TOC_LIKE_CHAPTER_RE.match(stripped):
            return True

        chapter_hits = re.findall(r"第\s*[一二三四五六七八九十百\d]+\s*章", cleaned)
        if len(chapter_hits) >= 2:
            return True

        section_hits = re.findall(r"第\s*[一二三四五六七八九十百\d]+\s*节", cleaned)
        if len(section_hits) >= 4:
            return True

        if "参考文献" in cleaned and ("后记" in cleaned or "目录" in cleaned):
            return True

        catalogue_words = ("封面", "扉页", "版权信息", "目录")
        if sum(1 for word in catalogue_words if word in cleaned) >= 2:
            return True

        return False

    def _parse_chapter_number(self, value: str) -> int | None:
        value = value.strip()
        if value.isdigit():
            return int(value)

        hundreds = 0
        if "百" in value:
            parts = value.split("百", 1)
            h_char = parts[0]
            hundreds = (self.CHINESE_NUMERAL_MAP.get(h_char, 1) if h_char else 1) * 100
            value = parts[1].lstrip("零")  # strip zero-placeholder (e.g. 一百零一 → 一)
            if not value:
                return hundreds

        if not value:
            return hundreds or None

        if value.startswith("十"):
            suffix = value[1:]
            return hundreds + 10 + self.CHINESE_NUMERAL_MAP.get(suffix, 0)
        if "十" in value:
            prefix, suffix = value.split("十", 1)
            tens = self.CHINESE_NUMERAL_MAP.get(prefix, 0) * 10
            ones = self.CHINESE_NUMERAL_MAP.get(suffix, 0) if suffix else 0
            return hundreds + tens + ones
        single = self.CHINESE_NUMERAL_MAP.get(value)
        return hundreds + single if single is not None else (hundreds or None)

    def _next_content_line(self, lines: list[str], start: int) -> tuple[int, str] | None:
        for idx in range(start, min(start + 5, len(lines))):
            stripped = lines[idx].strip()
            if not stripped:
                continue
            return idx, stripped
        return None

    def _resolve_boundary_title(
        self,
        lines: list[str],
        marker_index: int,
        inline_title: str | None,
    ) -> tuple[str, int]:
        if inline_title:
            return self._clean_heading_marker(inline_title), marker_index + 1

        next_line = self._next_content_line(lines, marker_index + 1)
        if next_line is None:
            return self._clean_heading_marker(lines[marker_index]), marker_index + 1

        line_idx, line = next_line
        heading_match = re.match(r"^#{1,6}\s+(.+)", line)
        title = heading_match.group(1).strip() if heading_match else line
        return title, line_idx + 1

    def _detect_special_boundary(self, line_index: int, stripped: str) -> ChapterBoundary | None:
        for pat in self.PREFACE_PATTERNS:
            if re.match(pat, stripped, re.IGNORECASE):
                title = self._clean_heading_marker(stripped)
                if len(title) > 80:
                    return None
                return ChapterBoundary(line_index, line_index + 1, "preface", title, None, title)

        for pat in self.AFTERWORD_PATTERNS:
            if re.match(pat, stripped, re.IGNORECASE):
                title = self._clean_heading_marker(stripped)
                if len(title) > 80:
                    return None
                return ChapterBoundary(line_index, line_index + 1, "afterword", title, None, title)

        return None

    def _score_boundary_candidate(
        self, stripped: str, title: str, body_start_line: int, lines: list[str]
    ) -> int:
        cleaned = self._clean_heading_marker(stripped)
        score = 0
        if stripped.startswith("#"):
            score += 3
        if re.match(r"^#{1,3}\s+", stripped):
            score += 1
        if title and not self._is_noise(title):
            score += 2
        if len(cleaned) <= 80:
            score += 1
        next_line = self._next_content_line(lines, body_start_line)
        if next_line is not None and len(self._clean_heading_marker(next_line[1])) >= 20:
            score += 1
        if self._is_toc_like_boundary_line(stripped):
            score -= 10
        return score

    def _find_chapter_boundary_candidates(
        self, lines: list[str]
    ) -> list[ChapterBoundaryCandidate]:
        candidates: list[ChapterBoundaryCandidate] = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if self._is_toc_like_boundary_line(stripped):
                continue

            special_boundary = self._detect_special_boundary(i, stripped)
            if special_boundary is not None:
                score = self._score_boundary_candidate(
                    stripped,
                    special_boundary.title,
                    special_boundary.body_start_line,
                    lines,
                )
                if score > 0:
                    candidates.append(ChapterBoundaryCandidate(
                        line_index=special_boundary.line_index,
                        body_start_line=special_boundary.body_start_line,
                        kind=special_boundary.kind,
                        marker=special_boundary.marker,
                        chapter_number=special_boundary.chapter_number,
                        title=special_boundary.title,
                        score=score,
                    ))
                continue

            chapter_match = self.CHINESE_CHAPTER_RE.match(stripped)
            marker_prefix = "第"
            inline_marker_text = None
            if chapter_match is None:
                chapter_match = self.ENGLISH_CHAPTER_RE.match(stripped)
                marker_prefix = "CHAPTER "
            if chapter_match is None:
                inline_match = self.INLINE_CHINESE_CHAPTER_RE.search(
                    self._clean_heading_marker(stripped)
                )
                if inline_match is not None:
                    chapter_match = inline_match
                    marker_prefix = "第"
                    inline_marker_text = inline_match.group("marker")
            if chapter_match is None:
                continue

            chapter_number = self._parse_chapter_number(chapter_match.group("num"))
            if chapter_number is None:
                continue

            if inline_marker_text:
                marker = inline_marker_text
                title = self._extract_inline_chapter_title(
                    self._clean_heading_marker(stripped),
                    marker,
                )
                body_start_line = i + 1
            else:
                title, body_start_line = self._resolve_boundary_title(
                    lines,
                    i,
                    chapter_match.groupdict().get("title"),
                )
                title = self._strip_section_suffix(title)
                marker = (
                    f"{marker_prefix}{chapter_match.group('num')}章"
                    if marker_prefix == "第"
                    else f"CHAPTER {chapter_number}"
                )

            if not title or self._is_noise(title):
                continue

            score = self._score_boundary_candidate(stripped, title, body_start_line, lines)
            if score <= 0:
                continue

            candidates.append(ChapterBoundaryCandidate(
                line_index=i,
                body_start_line=body_start_line,
                kind="chapter",
                marker=marker,
                chapter_number=chapter_number,
                title=title,
                score=score,
            ))

        candidates.sort(key=lambda c: c.line_index)
        return candidates

    def _select_numbered_chapter_boundaries(
        self,
        candidates: list[ChapterBoundaryCandidate],
    ) -> list[ChapterBoundaryCandidate]:
        numbered = [
            c for c in candidates
            if c.kind == "chapter" and c.chapter_number is not None
        ]
        by_number: dict[int, list[ChapterBoundaryCandidate]] = {}
        for candidate in numbered:
            by_number.setdefault(candidate.chapter_number, []).append(candidate)

        selected: list[ChapterBoundaryCandidate] = []
        last_line_index = -1
        expected = 1
        for number in sorted(by_number):
            if number > expected and selected:
                logger.warning(
                    "PDF chapter sequence skipped from %s to %s while selecting boundaries.",
                    expected,
                    number,
                )
            viable = [c for c in by_number[number] if c.line_index > last_line_index]
            if not viable:
                logger.warning(
                    "PDF chapter %s has no candidate after previous selected boundary.",
                    number,
                )
                continue
            best = max(viable, key=lambda c: (c.score, -c.line_index))
            selected.append(best)
            last_line_index = best.line_index
            expected = number + 1

        return selected

    def _select_chapter_boundaries(
        self,
        candidates: list[ChapterBoundaryCandidate],
    ) -> list[ChapterBoundaryCandidate]:
        numbered = self._select_numbered_chapter_boundaries(candidates)
        if not numbered:
            specials = [
                c for c in candidates
                if c.kind in {"preface", "afterword"} and c.score > 0
            ]
            specials.sort(key=lambda c: c.line_index)
            return specials

        first_numbered = numbered[0].line_index
        last_numbered = numbered[-1].line_index

        prefaces = [
            c for c in candidates
            if c.kind == "preface" and c.line_index < first_numbered and c.score > 0
        ]
        afterwords = [
            c for c in candidates
            if c.kind == "afterword"
            and c.line_index > last_numbered
            and c.score > 0
            and "参考文献" not in c.title
        ]

        prefaces.sort(key=lambda c: c.line_index)
        afterwords.sort(key=lambda c: c.line_index)

        result: list[ChapterBoundaryCandidate] = []
        result.extend(prefaces)
        result.extend(numbered)
        result.extend(afterwords)

        result.sort(key=lambda c: c.line_index)
        return result

    def _find_chapter_boundaries(self, lines: list[str]) -> list[ChapterBoundary]:
        candidates = self._find_chapter_boundary_candidates(lines)
        selected = self._select_chapter_boundaries(candidates)
        return [
            ChapterBoundary(
                line_index=c.line_index,
                body_start_line=c.body_start_line,
                kind=c.kind,
                marker=c.marker,
                chapter_number=c.chapter_number,
                title=c.title,
            )
            for c in selected
        ]

    def _split_markdown_into_chapters(self, markdown: str) -> list[RawChapter]:
        """Split pymupdf4llm Markdown into chapters using detected ChapterBoundary objects.

        Two-stage: detect clean ChapterBoundary objects, then resolve chapter segments.
        Supports Chinese chapter markers (第N章), English CHAPTER N, inline titles,
        heading+plain-title variants, and preface/afterword detection.
        """
        lines = markdown.split("\n")
        boundaries = self._find_chapter_boundaries(lines)

        if not boundaries:
            if len(markdown) > 5000:
                logger.warning("No chapter boundaries detected in large PDF markdown output.")
            return []

        chapters: list[RawChapter] = []
        for b_pos, boundary in enumerate(boundaries):
            start_idx = boundary.line_index
            end_idx = boundaries[b_pos + 1].line_index if b_pos + 1 < len(boundaries) else len(lines)
            segment_lines = lines[start_idx:end_idx]
            body_start = max(1, boundary.body_start_line - start_idx)

            text = "\n".join(segment_lines[body_start:]).strip()
            if len(text) < 100:
                continue

            chapters.append(RawChapter(
                chapter_num=len(chapters) + 1,
                title=boundary.title,
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
