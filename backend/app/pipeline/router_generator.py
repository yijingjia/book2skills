"""
主调度生成器 — 第 5 层核心管道
职责：汇总前序生成的所有 ModularSkills，撰写 SKILL.md (master router)
供大模型 Agent 在运行时识别意图并分发请求给各专精技能。
"""
import difflib
import json
import re
from pathlib import Path

from app.core.llm import close_llm_client, get_generation_model, get_llm_client
from app.core.retry import llm_retry
from app.schemas.schemas import MasterRouter, ModularSkill

# 读取指定的 Prompt 模板
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "generate_master_router.md"


class RouterGenerator:
    """基于所有生成的 Skills 构建顶层调度说明"""

    def __init__(self):
        self.client = get_llm_client()
        with open(PROMPT_PATH, encoding="utf-8") as f:
            self.prompt_template = f.read()

    async def aclose(self) -> None:
        await close_llm_client(self.client)

    async def generate_master_router(
        self,
        book_title: str,
        skills: list[ModularSkill],
    ) -> MasterRouter:
        """构建 Router 规则，由 @llm_retry 自动处理频率限制和网络超时重试。"""
        skills_meta = [
            {
                "skill_name": s.name,
                "description": s.description,
                "when_to_use": s.when_to_use,
            }
            for s in skills
        ]
        meta_json_str = json.dumps(skills_meta, ensure_ascii=False, indent=2)
        prompt = self.prompt_template.replace("{{ book_title }}", book_title)
        prompt = prompt.replace("{{ skills_meta_json }}", meta_json_str)
        schema_str = json.dumps(MasterRouter.model_json_schema(), ensure_ascii=False, indent=2)
        prompt = prompt.replace("{{ output_schema }}", schema_str)

        router = await self._call_llm(prompt)

        # 校验与纠错：确保 routing_rules 中的 target 与 skills 名对齐
        valid_names = [s.name for s in skills]
        sanitized_rules = {}
        for cond, target in router.routing_rules.items():
            matched_name = target
            if target not in valid_names:
                matches = difflib.get_close_matches(target, valid_names, n=1, cutoff=0.6)
                matched_name = matches[0] if matches else (valid_names[0] if valid_names else target)
            safe_target = re.sub(r'[^\w\-_.]', '_', matched_name).replace(' ', '_')
            sanitized_rules[cond] = safe_target
        router.routing_rules = sanitized_rules
        return router

    @llm_retry
    async def _call_llm(self, prompt: str) -> MasterRouter:
        """实际的 LLM 调用，使用 tenacity retry 装饰"""
        response = await self.client.chat.completions.create(
            model=get_generation_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw_result = response.choices[0].message.content
        data = json.loads(raw_result)
        return MasterRouter(**data)

    def render_router_md(self, router: MasterRouter, book_title: str) -> str:
        """将 MasterRouter 模型渲染为可读的 Markdown 格式"""
        lines = [
            "# Agent 主调度指南",
            f"\n> 基于《{book_title}》的方法论提炼",
            f"\n## 你的角色设定 (Agent Instruction)\n{router.agent_instruction}\n",
            "## 多意图识别与技能路由规则 (Routing Rules)",
            "\n当用户提问时，请分析其核心意图，并严格执行以下路由规则调用特定的技能文件：\n"
        ]

        for condition, skill_target in router.routing_rules.items():
            lines.append(f"- **当遇到场景/问题**: {condition}")
            lines.append(f"  👉 **请调用执行**: `skills/{skill_target}.md`\n")

        return "\n".join(lines)

    def save_router_md(self, router_md: str, output_dir: str) -> str:
        """将 SKILL.md 写入根目录 (作为库的主入口)"""
        path = Path(output_dir) / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(router_md, encoding="utf-8")
        return str(path)
