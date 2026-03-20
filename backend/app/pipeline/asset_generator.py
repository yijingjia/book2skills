"""
资源生成器 (Asset Generator)
在 SKILL.md 生成之后，从工作流和原文上下文中提取：
1. 可执行逻辑（如计算规则、评分标准） -> 转化为 scripts/ 脚本
2. 输出格式（如分析框架、报告模板） -> 转化为 templates/ 模板
"""
import ast
import json
import logging

from app.core.llm import get_generation_model, get_llm_client

logger = logging.getLogger(__name__)

ASSET_GENERATION_PROMPT = """你是一个高级系统架构师和知识转化专家。我们已经通过原书内容提炼出了 Agent 的执行指令（SKILL.md）。
现在，请你需要仔细阅读已经生成的【工作流】和【原文上下文】，把书里提到的“判断逻辑/计算公式”转化为 Python 脚本，把“分析框架/报告结构”转化为 Markdown 模板。

## 输入资料
书名：{book_title}

【已生成的 SKILL.md 工作流】
{skill_workflow}

【原书核心上下文】
{context}

## 你的任务
1. **提取 Scripts (执行脚本)**:
   - 寻找书中有**明确规则**的逻辑。例如：条件评估标准、指标计算公式、打分问卷。
   - 不要瞎编逻辑。如果原文没有给出具体的计算或判断标准，**强制为空**。
   - 所有生成的代码必须是合法的 Python 代码，包含清晰的注释和 `def main(*args, **kwargs):` 入口。

2. **提取 Templates (输出模板)**:
   - 寻找书中要求遵循的**特定结构或框架**。例如：“空·雨·伞”问题分析报告、特定格式的诊断表单。
   - 使用 Markdown 格式。在需要 Agent 动态填写的地方使用占位符，如 `[Agent 填写事实数据]`。
   - 如果原文没有特定的输出格式要求，**强制为空**。

## 严格输出限制
必须输出严格的 JSON 格式（不要附带额外的 Markdown 标记开头/结尾，只输出裸 JSON 字符串）：
{{
  "scripts": {{
    "evaluate_logic.py": "def main(answers: dict):\\n    '''根据第一章的标准评估分数'''\\n    score = 0\\n    # ...\\n    return score"
  }},
  "templates": {{
    "analysis_report.md": "# 分析报告\\n\\n## 1. 现状\\n[填写现状]"
  }}
}}

如果没有任何需要提取的脚本，`scripts` 请输出 `{{}}`。
如果没有任何特定的格式要求，`templates` 请输出 `{{}}`。
注意处理 JSON 字符串中代码或 markdown 的换行与转义符号。"""

class AssetGenerator:
    """提取和生成 skills.zip 所需的 scripts 和 templates 资产"""

    def __init__(self):
        self.client = get_llm_client()

    async def generate_assets(
        self,
        book_title: str,
        skill_workflow: str,
        context: str,
    ) -> tuple[dict[str, str], dict[str, str]]:
        """
        生成脚本和模板。

        Args:
            book_title: 书名
            skill_workflow: 已经生成的 SKILL.md 中的工作流部分或全文
            context: RAG 获取的原书核心上下文

        Returns:
            (scripts_dict, templates_dict) 元组
        """
        prompt = ASSET_GENERATION_PROMPT.format(
            book_title=book_title,
            skill_workflow=skill_workflow,
            context=context,
        )

        try:
            response = await self.client.chat.completions.create(
                model=get_generation_model(),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            raw_output = response.choices[0].message.content
            if not raw_output:
                return {}, {}

            data = json.loads(raw_output)
            scripts = data.get("scripts", {})
            templates = data.get("templates", {})

            # 简单的代码安全验证与格式化
            valid_scripts = {}
            for filename, code in scripts.items():
                if filename.endswith(".py"):
                    try:
                        ast.parse(code)
                        valid_scripts[filename] = code
                    except Exception as e:
                        logger.warning(f"Generated script {filename} contains syntax errors and will be dropped. Error: {e}")
                else:
                    valid_scripts[filename] = code

            return valid_scripts, templates

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse asset generation JSON output: {e}")
            return {}, {}
        except Exception as e:
            logger.error(f"Error during asset generation: {e}")
            return {}, {}
