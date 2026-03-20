# book2skills

[English README](README.en.md)

将 EPUB 书籍自动转换为可安装到 AI Agent 的技能包（`skills.zip`）。

## 项目简介

`book2skills` 是一个面向知识工作流的全栈项目：上传一本书后，系统会完成解析、分块、知识单元抽取、技能生成与打包，最终产出可直接用于 Agent 的结构化技能包。

核心能力：
- 文档处理：支持 EPUB 上传与章节化解析。
- RAG 检索：基于 Qdrant 做书籍 chunk 检索与问答。
- 技能生产：生成模块化技能 + Router，并沉淀到数据库与向量库。
- 可下载交付：输出标准 `skills.zip`，便于离线或跨平台使用。
- 网页内直接使用：除了下载技能包，还可在 Web 页面中直接与书对话（RAG 查询），并调用已生成技能进行对话式推演。

## 技术栈

- 前端：Next.js 14、TypeScript、Tailwind CSS、shadcn/ui
- 后端：FastAPI、SQLAlchemy、Alembic、Celery、Redis
- 存储与检索：PostgreSQL、Qdrant、本地/S3 存储
- AI：OpenAI / Qwen / GLM（通过环境变量选择）

## 快速开始（仅 Docker）

### 1) 准备环境变量

```bash
cp .env.example .env
```

至少需要确认：
- `DATABASE_URL`
- `LLM_PROVIDER` 与对应的 API Key（如 `OPENAI_API_KEY` / `QWEN_API_KEY` / `GLM_API_KEY`）

### 2) 启动服务

```bash
docker compose up -d
```

默认地址：
- 前端：`http://localhost:3000`
- 后端 API：`http://localhost:8000`
- OpenAPI 文档：`http://localhost:8000/docs`
- Qdrant Dashboard：`http://localhost:6333/dashboard`

### 3) 查看日志（可选）

```bash
docker compose logs -f backend worker frontend
```

## 测试

```bash
docker compose exec backend pytest tests/ -v --cov=app
```

## 核心 API

### 书籍
- `GET /api/books`：书籍列表
- `POST /api/books/upload`：上传书籍
- `GET /api/books/{book_id}/status`：处理状态
- `GET /api/books/{book_id}/chapters`：章节信息

### 技能包
- `POST /api/skills/books/{book_id}/generate`：触发异步生成
- `GET /api/skills/{skill_id}`：技能包详情
- `POST /api/skills/{skill_id}/pack`：打包 zip
- `GET /api/skills/{skill_id}/download`：下载 zip

### 对话与问答
- `POST /api/chat/books/{book_id}/qa`：书籍问答（RAG 查询，JSON）
- `POST /api/chat/skills/{skill_id}/playground`：调用技能进行对话式推演（SSE）
- `POST /api/chat/skills/{skill_id}/refine`：技能精炼（SSE）

## `skills.zip` 结构

```text
skills.zip
├── SKILL.md
├── skills/
├── scripts/
├── references/
├── templates/
└── manifest.json
```

## 仓库结构

```text
book2skills/
├── backend/          # FastAPI + Pipeline + Celery
├── frontend/         # Next.js UI
├── docs/             # PRD / Architecture / Code Standards
├── compose.yaml      # Docker Compose 配置
└── .env.example      # 环境变量模板
```

## 状态说明

项目仍在快速迭代中，接口与目录可能持续演进。建议在接入前以 `http://localhost:8000/docs` 的 OpenAPI 为准进行校验。当前文档仅保证 Docker 工作流。

## 已知 Issue

- 当前实际稳定支持的输入格式为 **EPUB**（PDF 流程尚未完整验证）。
- 当前仅测试过**中文书籍**，其他语言书籍尚未系统验证。
