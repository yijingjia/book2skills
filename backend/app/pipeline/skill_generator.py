"""
独立 Skill 生成器 — 第 4 层核心管道
职责：将提取出来的细碎片断 KnowledgeUnit (KU) 进行聚类和提炼，
生成 Agent 可直接调用的标准化方法论字典 (ModularSkill)。
"""
import json
from pathlib import Path

from app.core.llm import close_llm_client, get_generation_model, get_llm_client
from app.core.retry import llm_retry
from app.schemas.schemas import KnowledgeUnit, ModularSkill

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "generate_modular_skill.md"



SKILL_MD_PROMPT = """你是一个严格基于原文的知识提取专家，专门生成可被 AI Agent 执行的技能定义文件（SKILL.md）。

## 绝对规则（违反则输出无效）
1. 只能使用 <context> 标签中提供的原文内容，禁止使用 context 以外的任何知识
2. 如果原文未明确提及某内容，必须省略该内容，不得推断或补充
3. 每个步骤必须包含 source_quote 字段（从原文摘抄的句子）
4. 工作流步骤必须是 Agent 可直接执行的具体指令，不能含糊

## 书籍信息
书名：{book_title}
重点章节：{chapter_titles}
用户目标：{user_goal}

## 原文内容
<context>
{context}
</context>

## 输出要求
严格按照以下 JSON 格式输出，不要添加任何额外文字或 markdown：
{{
  "skill_title": "技能名称（基于书中方法论，不超过20字）",
  "skill_description": "1-2句话描述这个技能能做什么",
  "applicable_scenarios": ["场景1", "场景2", "场景3"],
  "workflow": [
    {{
      "step_num": 1,
      "action": "具体的操作指令（20-100字）",
      "detail": "补充说明（可选）",
      "condition": "触发条件（可选，如：当用户遇到XX时）",
      "source_quote": "从原文中摘抄的相关句子（必填）",
      "source_chapter": "第X章 章节标题",
      "source_page": null
    }}
  ],
  "references_keywords": ["关键词1", "关键词2"],
  "key_concepts": ["核心概念1", "核心概念2"],
  "constraints": ["使用限制1（例如：只能引用 references/ 中的内容）"]
}}"""


class SkillGenerator:
    """基于知识单元生成精炼模块化 Skill"""

    def __init__(self):
        self.client = get_llm_client()
        with open(PROMPT_PATH, encoding="utf-8") as f:
            self.prompt_template = f.read()

    async def aclose(self) -> None:
        await close_llm_client(self.client)

    async def generate_modular_skill(
        self,
        book_title: str,
        knowledge_units: list[KnowledgeUnit],
        theme_hint: str | None = None,
    ) -> ModularSkill:
        """从 KUs 生成 ModularSkill，由 @llm_retry 自动处理频率限制和网络超时重试。"""
        # 将 KUs 转成紧凑的 JSON 字符串供 LLM 阅读
        ku_dicts = [ku.model_dump() for ku in knowledge_units]
        ku_json_str = json.dumps(ku_dicts, ensure_ascii=False, indent=2)

        prompt = self.prompt_template.replace("{{ book_title }}", book_title)
        prompt = prompt.replace("{{ knowledge_units_json }}", ku_json_str)
        schema_str = json.dumps(ModularSkill.model_json_schema(), ensure_ascii=False, indent=2)
        prompt = prompt.replace("{{ output_schema }}", schema_str)

        if theme_hint:
            prompt += (
                f"\n\n[聚类主题提示] 这批 KU 已由向量聚类识别为属于「{theme_hint}」主题。"
                " 请优先围绕此方向确定技能名称与核心步骤，避免生成过于宽泛的通用标题。"
            )

        return await self._call_llm(prompt)

    @llm_retry
    async def _call_llm(self, prompt: str) -> ModularSkill:
        """实际的 LLM 调用，使用 tenacity retry 装饰"""
        response = await self.client.chat.completions.create(
            model=get_generation_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        skill_data = json.loads(raw)
        self._validate_skill_data(skill_data)
        return ModularSkill(**skill_data)


    def _validate_skill_data(self, data: dict) -> None:
        # 防幻觉：验证生成的 SkillStep 是否夹带私货（缺失 source_quote）
        for step in data.get("thinking_steps", []):
            if not step.get("source_quote"):
                raise ValueError(
                    f"步骤 {step.get('step_num')} 缺少 source_quote，"
                    "该步骤可能包含幻觉内容，已拒绝输出。"
                )

    def render_skill_md(self, skill: ModularSkill, book_title: str) -> str:
        """将生成的 ModularSkill 模型渲染为易读的 Markdown 格式供最终打包"""
        lines = [
            f"# {skill.name}",
            f"\n> 基于《{book_title}》提取\n",
            f"## 技能描述 (Description)\n{skill.description}\n",
            "## 适用场景 (When to Use)",
        ]
        for s in skill.when_to_use:
            lines.append(f"- {s}")

        lines.append("\n## 核心思维步骤 (Thinking Steps)")
        lines.append("\n> Agent 必须严格按照以下步骤执行分析框架：\n")

        for step in skill.thinking_steps:
            lines.append(f"{step.step_num}. **{step.action}**")
            if step.condition:
                lines.append(f"   - *触发条件*: {step.condition}")
            if step.detail:
                lines.append(f"   - *详情*: {step.detail}")
            lines.append(f"   - 📖 *依据 ({step.source_chapter})*: {step.source_quote}\n")

        lines.append("## 原文依据与溯源 (References)")
        lines.append("用于离线 RAG 的检索关键词：")
        for kw in skill.references_keywords:
            lines.append(f"- {kw}")

        # 自动汇总本技能涉及的书中章节与理论出处
        lines.append("\n## 本技能核心理论出处 (Theory Sources)")
        lines.append(
            "> Agent 在回答用户时，**必须在回答末尾**附上「📖 本次分析引用的书中理论依据」，"
            "列出实际用到的理论名称及其来源章节（从本节和每个步骤的 source_chapter 中取）。"
        )
        # 收集所有步骤的章节来源（去重保序）
        seen_chapters: set[str] = set()
        unique_chapters: list[str] = []
        for step in skill.thinking_steps:
            if step.source_chapter and step.source_chapter not in seen_chapters:
                seen_chapters.add(step.source_chapter)
                unique_chapters.append(step.source_chapter)
        if unique_chapters:
            lines.append("\n本技能的分析框架源自以下章节：")
            for ch in unique_chapters:
                lines.append(f"- {ch}")
        if skill.references_keywords:
            lines.append("\n本技能涵盖的核心理论/概念（可直接在引用清单中使用）：")
            for kw in skill.references_keywords:
                lines.append(f"- {kw}")

        return "\n".join(lines)

    def save_skill_md(self, skill_md: str, skill_name: str, output_dir: str) -> str:
        """将单个 Skill.md 写入 skills/ 目录"""
        path = Path(output_dir) / f"{skill_name}.md"
        path.write_text(skill_md, encoding="utf-8")
        return str(path)
