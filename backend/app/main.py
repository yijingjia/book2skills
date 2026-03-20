import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import books, chat, skills
from app.core.config import settings

# 配置基础日志，确保 INFO 级别和以上内容能输出到 console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 数据库表结构由 Alembic 管理，启动前请确保已执行 `alembic upgrade head`
    # 本函数保留 lifespan hook 供后续扩展（如连接池预热、健康检查等）
    yield


app = FastAPI(
    title="book2skills API",
    description="将 PDF/EPUB 书籍转换为可执行 Agent 技能包",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books.router)
app.include_router(skills.router)
app.include_router(chat.router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
