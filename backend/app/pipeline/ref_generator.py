"""
references/ 目录生成器 — 将分块后的章节内容导出为离线可用的 Markdown 文件
这些文件会被打入 skills.zip，供 Agent 运行时动态加载
"""
import json
import re
from pathlib import Path

from app.pipeline.parser import RawChapter


class ReferenceGenerator:
    """将书籍章节生成 references/ 目录结构"""

    def generate(
        self,
        chapters: list[RawChapter],
        output_dir: str,
        book_title: str,
    ) -> dict:
        """
        生成 references/ 目录。

        Args:
            chapters: 解析后的章节列表
            output_dir: 输出目录路径（skills.zip 内的 references/）
            book_title: 书名，用于生成 index.json

        Returns:
            index 字典（同时写入 index.json）
        """
        ref_path = Path(output_dir) / "references"
        ref_path.mkdir(parents=True, exist_ok=True)

        index = {
            "book_title": book_title,
            "total_chapters": len(chapters),
            "chapters": [],
        }

        for chapter in chapters:
            filename = self._make_filename(chapter.chapter_num, chapter.title)
            chapter_path = ref_path / filename

            # 写入章节 Markdown 文件
            content = self._format_chapter(chapter)
            chapter_path.write_text(content, encoding="utf-8")

            # 同时生成摘要版（前300字，供 Agent 快速判断相关性）
            summary_filename = filename.replace(".md", "_summary.md")
            summary_path = ref_path / summary_filename
            summary_content = self._format_summary(chapter)
            summary_path.write_text(summary_content, encoding="utf-8")

            index["chapters"].append({
                "chapter_num": chapter.chapter_num,
                "title": chapter.title,
                "page_start": chapter.page_start,
                "page_end": chapter.page_end,
                "file": filename,
                "summary_file": summary_filename,
                "char_count": len(chapter.text),
            })

        # 写入 index.json
        index_path = ref_path / "index.json"
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

        return index

    def _make_filename(self, chapter_num: int, title: str) -> str:
        """生成安全的文件名"""
        safe_title = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", title)[:30]
        return f"ch{chapter_num:02d}_{safe_title}.md"

    def _format_chapter(self, chapter: RawChapter) -> str:
        lines = [
            f"# 第 {chapter.chapter_num} 章：{chapter.title}",
        ]
        if chapter.page_start and chapter.page_end:
            lines.append(f"> 页码：P{chapter.page_start} - P{chapter.page_end}\n")
        lines.append("")
        lines.append(chapter.text)
        return "\n".join(lines)

    def _format_summary(self, chapter: RawChapter) -> str:
        preview = chapter.text[:300].strip()
        if len(chapter.text) > 300:
            preview += "..."
        return (
            f"# 摘要：第 {chapter.chapter_num} 章 — {chapter.title}\n\n"
            f"{preview}\n\n"
            f"---\n完整内容见：ch{chapter.chapter_num:02d}_{chapter.title[:30]}.md"
        )
