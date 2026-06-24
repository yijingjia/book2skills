"""
skills.zip 打包器 — 将生成的各组件打包为标准技能包
"""
import json
import zipfile
from pathlib import Path


def _zip_content(content):
    if isinstance(content, (dict, list)):
        return json.dumps(content, ensure_ascii=False, indent=2)
    return content


class MissingReferencesError(FileNotFoundError):
    pass


class SkillPacker:
    """将 SKILL.md、scripts/、references/、templates/ 打包为 skills.zip"""

    def pack(
        self,
        skill_md: str,
        references_dir: str,
        scripts: dict | None,
        templates: dict | None,
        output_path: str,
        book_title: str,
        require_references: bool = False,
    ) -> str:
        """
        打包 skills.zip。

        Args:
            skill_md: SKILL.md 内容字符串
            references_dir: references/ 目录路径
            scripts: scripts 文件字典 {filename: content}
            templates: templates 文件字典 {filename: content}
            output_path: 输出 zip 文件路径
            book_title: 书名（写入 manifest）

        Returns:
            输出文件的绝对路径
        """
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        ref_path = Path(references_dir) / "references"
        if require_references and not ref_path.exists():
            raise MissingReferencesError(f"references directory not found: {ref_path}")

        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1. 解析 skill_md 提取出 Router 的部分
            # 由于在 routes/skills.py 中我们用的分隔符是 '\n\n---\n\n', 第一部分必定是 Router (作为总控)
            parts = skill_md.split("\n\n---\n\n")
            master_router_md = parts[0] if parts else skill_md
            zf.writestr("SKILL.md", master_router_md)

            # 2. references/
            if ref_path.exists():
                for file in ref_path.rglob("*"):
                    if file.is_file():
                        arcname = f"references/{file.relative_to(ref_path)}"
                        zf.write(file, arcname)

            # 3. skills/ 独立技能包 以及 scripts/ (临时过滤)
            has_skills = False
            has_scripts = False
            if scripts:
                for filename, content in scripts.items():
                    if filename.startswith("skill_") and filename.endswith(".md"):
                        # 去掉 'skill_X_' 的前缀，作为干净的技能文件名
                        import re
                        clean_name = re.sub(r'^skill_\d+_', '', filename)
                        zf.writestr(f"skills/{clean_name}", _zip_content(content))
                        has_skills = True
                    else:
                        zf.writestr(f"scripts/{filename}", _zip_content(content))
                        has_scripts = True

            if not has_skills:
                zf.writestr(
                    "skills/README.md",
                    "# skills/\n\n此书籍提取出的子技能尚未生成。\n"
                )
            if not has_scripts:
                # 写入占位说明文件
                zf.writestr(
                    "scripts/README.md",
                    "# scripts/\n\n此技能暂无自动生成的脚本。\n"
                    "可在此目录添加自定义执行逻辑。",
                )

            # 4. templates/
            if templates:
                for filename, content in templates.items():
                    zf.writestr(f"templates/{filename}", _zip_content(content))
            else:
                zf.writestr(
                    "templates/README.md",
                    "# templates/\n\n此技能暂无交互模板。\n"
                    "可在此目录添加自定义输出模板。",
                )

            # 5. manifest.json（技能包元信息）
            manifest = {
                "name": book_title,
                "version": "1.0.0",
                "generated_by": "book2skills",
                "structure": {
                    "router": "SKILL.md",
                    "skills": "skills/",
                    "scripts": "scripts/",
                    "references": "references/",
                    "templates": "templates/",
                },
                "usage": (
                    "将此技能包安装到支持的 AI Agent 平台，"
                    "系统级 Agent 将自动读取 SKILL.md 并根据策略按需调用 skills/ 下的工具。"
                ),
            }
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        return str(output.absolute())

    def get_zip_size_mb(self, zip_path: str) -> float:
        return Path(zip_path).stat().st_size / (1024 * 1024)
