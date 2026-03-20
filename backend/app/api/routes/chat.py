"""API 路由 — 对话精炼 & 书籍问答（SSE 流式输出）"""
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.llm import get_chat_model, get_llm_client
from app.models.models import Conversation, SkillPackage
from app.pipeline.refiner import SkillRefiner
from app.pipeline.retriever import LowConfidenceError, RAGRetriever
from app.schemas.schemas import PlaygroundRequest, QARequest, QAResponse, RefineRequest

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/skills/{skill_id}/refine")
async def refine_skill(
    skill_id: uuid.UUID,
    request: RefineRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    对话式精炼 SKILL.md（SSE 流式响应）
    用户通过自然语言指令迭代调整技能定义
    """
    result = await db.execute(
        select(SkillPackage).where(SkillPackage.id == skill_id)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(404, detail="技能包不存在")

    # 获取对话历史
    history_result = await db.execute(
        select(Conversation)
        .where(Conversation.skill_package_id == skill_id)
        .order_by(Conversation.created_at)
        .limit(20)
    )
    history = [
        {"role": h.role, "content": h.content}
        for h in history_result.scalars().all()
    ]

    # 保存用户消息
    user_msg = Conversation(
        skill_package_id=skill_id,
        role="user",
        content=request.instruction,
    )
    db.add(user_msg)
    await db.commit()

    refiner = SkillRefiner()
    collected_response = []

    async def stream_generator():
        async for chunk in refiner.refine_stream(
            book_id=str(skill.book_id),
            current_skill_md=skill.skill_md or "",
            instruction=request.instruction,
            conversation_history=history,
        ):
            collected_response.append(chunk)
            json_chunk = {"content": chunk}
            yield f"data: {json.dumps(json_chunk, ensure_ascii=False)}\n\n"

        # 流结束后保存完整回复并更新 SKILL.md
        full_response = "".join(collected_response)
        async with db.begin():
            assistant_msg = Conversation(
                skill_package_id=skill_id,
                role="assistant",
                content=full_response,
            )
            db.add(assistant_msg)
            skill.skill_md = full_response
            skill.version += 1
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@router.post("/skills/{skill_id}/playground")
async def skill_playground(
    skill_id: uuid.UUID,
    request: PlaygroundRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    技能推演沙盘 — 将 SKILL.md 作为 System Prompt 注入，纯模拟 Agent 执行
    """
    result = await db.execute(
        select(SkillPackage).where(SkillPackage.id == skill_id)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(404, detail="技能包不存在")

    if not skill.skill_md:
        raise HTTPException(400, detail="该书尚未生成技能包")

    client = get_llm_client()
    chat_model = get_chat_model()

    # 增强：基于向量检索的 Skill Engine OS 动态推演架构
    # 从原先强行加载整篇 SKILL.md，改为由 Retrieval Layer(检索层) 取回 TopK 子技能
    from app.pipeline.retriever import SkillRetriever
    retriever = SkillRetriever()

    # 因为用户不仅会提供当下的问题，其上下文也很重要，我们把最近的消息拼接来检索更好
    search_query = request.message
    if len(request.history) > 0:
         # 取最后一条助手/用户的上下文来辅助检索
         search_query = f"{request.history[-1].content}\n{request.message}"

    target_book_id = str(skill.book_id) if skill.book_id else None
    retrieved_skills = await retriever.retrieve(
        query=search_query,
        top_k=8,
        book_id=target_book_id
    )

    # 抽取总线路由字典做补充上下文
    parts = (skill.skill_md or "").split("\n\n---\n\n")
    master_router = parts[0] if len(parts) > 0 else "未定义路由"

    # 如果检索到了专精技能，把它序列化为详细字典字符串装箱
    if retrieved_skills:
        # 这里为了完整步骤描述，我们可以回表查询 Postgres 取出 workflow JSON，或者要求 Qdrant payload 冗余存一份
        # 由于咱们目前 DB 和操作还没完全解耦完成，如果是简单的 MVP，我们这里从 Payload 抓取最简摘要。
        # 稳妥起见，我们根据 retrieved_skills 的 IDs 查询 Postgres 里的具体 Workflow。
        from app.models.models import Skill

        skill_ids = [uuid.UUID(s.skill_id) for s in retrieved_skills]
        db_skills_result = await db.execute(select(Skill).where(Skill.id.in_(skill_ids)))
        db_skills = db_skills_result.scalars().all()

        detailed_skills = ""
        for s in db_skills:
             workflow_str = json.dumps(s.workflow, ensure_ascii=False, indent=2)
             detailed_skills += f"### 模块名: {s.name}\n- 描述: {s.description}\n- 适用场景: {s.when_to_use}\n- 标准执行流(Workflow): \n{workflow_str}\n\n"
    else:
        # 降级：如果向量库为空，说明可能是旧包，回退到原逻辑解析文本
        detailed_skills = "\n\n".join(parts[1:]) if len(parts) > 1 else ""

    system_prompt = (
        "你是一个极其专业的 AI Agent，专门负责执行从书籍中提取的专业技能。\n\n"
        "### 1. 核心导航器 (Master Router)\n"
        "以下是你处理任务的总线逻辑，请仔细阅读以理解当前技能集的全局概览：\n"
        f"{master_router}\n\n"
        "### 2. 相关技能库 (Relevant Skills)\n"
        "针对用户的当前场景，系统为你动态检索并加载了最高度匹配的几个子技能模块，请在以下库中获取标准干预步骤：\n"
        f"{detailed_skills}\n\n"
        "### 3. 执行规范\n"
        "- **精准打击**：在回答用户问题前，请优先调用被弹出的“相关技能库”里的步骤。如果库里空空如也，你可以仅依靠 Master Router 进行常识推演。\n"
        "- **分步推演**：严格执行详细技能库中的 Workflow 规划。如果提示了 Step 1, Step 2，请在回答中显式体现这些步骤并进行现实难题的缝合。\n"
        "- **专业性**：保持书中所传达的专业语调，将抽象的理论转化为用户可操作的建议。\n"
        "- **格式规范**：**必须使用 Markdown 格式**进行回复（包括标题、加粗、列表、表格等）。\n"
        "- **隐藏技术细节**：在给用户的正式回复中，**严禁**直接提及技能的名称（如 `Skill_Name_xxx`）。你应该将其转化为书中的理论阐述、分析方法或具体拆解动作。技能名称仅限在 `<thought>` 标签中使用。\n"
        "- **思维链**：你可以在正式回答前输出 `<thought> 你的规划 </thought>` 标签来展示你选中了哪条技能。"
    )

    # 构造对话历史
    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]
    for msg in request.history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": request.message})

    async def stream_generator():
        try:
            response_stream = await client.chat.completions.create(
                model=chat_model,
                messages=messages,
                stream=True,
            )

            async for chunk in response_stream:
                content = chunk.choices[0].delta.content
                if content:
                    json_chunk = {"content": content}
                    yield f"data: {json.dumps(json_chunk, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [Error] 推演意外中断: {str(e)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@router.post("/books/{book_id}/qa", response_model=QAResponse)
async def book_qa(
    book_id: uuid.UUID,
    request: QARequest,
    db: AsyncSession = Depends(get_db),
):
    """
    书籍问答 — 基于混合检索（向量 + BM25 重排）的原文问答
    防幻觉：检索为空时明确拒绝回答
    """
    retriever = RAGRetriever()

    try:
        # Use hybrid retrieval: wider candidate pool + BM25 rerank
        # This recovers chunks where the keyword exists but vector similarity is diluted
        chunks = await retriever.retrieve_hybrid(
            query=request.question,
            book_id=str(book_id),
            top_k=settings.RETRIEVAL_TOP_K,
            candidate_k=getattr(settings, "RETRIEVAL_CANDIDATE_K", 50),
        )
    except LowConfidenceError:
        return QAResponse(
            answer=f"抱歉，本书中未找到与「{request.question}」直接相关的内容。"
                   "请尝试换一个问题，或确认该内容是否在书中有所提及。",
            sources=[],
        )

    context = "\n\n---\n\n".join(
        f"[{c.chapter_title}]\n{c.text}" for c in chunks
    )

    client = get_llm_client()
    chat_model = get_chat_model()
    response = await client.chat.completions.create(
        model=chat_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是一个严格基于原文的知识问答助手。"
                    "只能使用 <context> 中的内容回答，禁止使用任何其他知识。"
                    "如果 context 中没有相关信息，回答「本书未提及此内容」。"
                ),
            },
            {
                "role": "user",
                "content": f"<context>\n{context}\n</context>\n\n问题：{request.question}",
            },
        ],
    )

    return QAResponse(
        answer=response.choices[0].message.content,
        sources=[
            {
                "chapter": c.chapter_title,
                "page": c.page_start,
                "quote": c.text[:150] + "..." if len(c.text) > 150 else c.text,
                "score": round(c.score, 3),
            }
            for c in chunks
        ],
    )
