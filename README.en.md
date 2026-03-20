# book2skills

[中文 README](README.md)

Convert EPUB books into installable AI Agent skill bundles (`skills.zip`).

## Overview

`book2skills` is a full-stack pipeline that turns a book into structured, reusable agent skills.
After upload, the system parses chapters, extracts knowledge units, generates modular skills, and packages everything into a downloadable bundle.

Key capabilities:
- Document ingestion: EPUB upload and chapter-aware parsing.
- RAG retrieval: Qdrant-based retrieval for book QA and grounding.
- Skill generation: modular skills + router generation with database/vector persistence.
- Deliverable output: standardized `skills.zip` for offline or cross-platform usage.
- Direct web interaction: besides downloading the skill bundle, you can chat with the book in the web app (RAG query) and invoke generated skills for interactive simulation.

## Tech Stack

- Frontend: Next.js 14, TypeScript, Tailwind CSS, shadcn/ui
- Backend: FastAPI, SQLAlchemy, Alembic, Celery, Redis
- Storage & retrieval: PostgreSQL, Qdrant, local/S3 storage
- AI providers: OpenAI / Qwen / GLM (selected by env vars)

## Quick Start (Docker Only)

### 1) Prepare environment variables

```bash
cp .env.example .env
```

At minimum, confirm:
- `DATABASE_URL`
- `LLM_PROVIDER` and its matching API key (`OPENAI_API_KEY` / `QWEN_API_KEY` / `GLM_API_KEY`)

### 2) Start services

```bash
docker compose up -d
```

Default URLs:
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- OpenAPI docs: `http://localhost:8000/docs`
- Qdrant dashboard: `http://localhost:6333/dashboard`

### 3) View logs (optional)

```bash
docker compose logs -f backend worker frontend
```

## Testing

```bash
docker compose exec backend pytest tests/ -v --cov=app
```

## Core APIs

### Books
- `GET /api/books`: list books
- `POST /api/books/upload`: upload a book
- `GET /api/books/{book_id}/status`: processing status
- `GET /api/books/{book_id}/chapters`: chapter list

### Skill Packages
- `POST /api/skills/books/{book_id}/generate`: trigger async generation
- `GET /api/skills/{skill_id}`: get skill package details
- `POST /api/skills/{skill_id}/pack`: create zip package
- `GET /api/skills/{skill_id}/download`: download zip package

### Chat & QA
- `POST /api/chat/books/{book_id}/qa`: book QA (RAG query, JSON)
- `POST /api/chat/skills/{skill_id}/playground`: skill-based interactive simulation (SSE)
- `POST /api/chat/skills/{skill_id}/refine`: skill refinement (SSE)

## `skills.zip` Structure

```text
skills.zip
├── SKILL.md
├── skills/
├── scripts/
├── references/
├── templates/
└── manifest.json
```

## Repository Layout

```text
book2skills/
├── backend/          # FastAPI + pipeline + Celery
├── frontend/         # Next.js UI
├── docs/             # PRD / architecture / coding standards
├── compose.yaml      # Docker Compose config
└── .env.example      # environment template
```

## Project Status

The project is under active development. APIs and structures may evolve.
Please treat `http://localhost:8000/docs` as the source of truth before integration. The documented workflow is Docker-first (and currently Docker-only).

## Known Issues

- The only input format that is currently stable in practice is **EPUB** (the PDF flow is not fully validated yet).
- Testing has only been performed with **Chinese books**; other languages have not been systematically validated yet.
