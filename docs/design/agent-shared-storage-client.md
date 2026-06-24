# Agent Shared Storage Client

This guide explains how an external agent can use Book2Skills as a shared storage system.

The service does not run the agent. The agent reads parsed book content from Book2Skills, generates a structured skill payload in its own context, then writes that payload back into the same Postgres/Qdrant/storage surfaces used by the existing app.

## Flow

1. Start Book2Skills backend, worker, frontend, Postgres, Redis, and Qdrant.
2. Upload a book through the web UI or CLI.
3. Wait until the book status is `ready`.
4. Read parsed content with `content mode=index`.
5. Read selected chapter bodies with `content mode=chapter`.
6. Extract comprehensive book-level knowledge units.
7. Ingest the knowledge units.
8. Generate a structured payload matching `AgentSkillIngestRequest`.
9. Ingest the skill payload.
10. Open the existing UI and use the resulting ready skill package.

## CLI

Run commands from the repo root:

```bash
cd backend
uv run python scripts/book2skills_agent.py list-books
```

Upload a book:

```bash
cd backend
uv run python scripts/book2skills_agent.py upload /absolute/path/to/book.pdf --wait
```

Read the book index:

```bash
cd backend
uv run python scripts/book2skills_agent.py content <book_id> --mode index
```

Read one chapter:

```bash
cd backend
uv run python scripts/book2skills_agent.py content <book_id> --mode chapter --chapter-num 1 --output /tmp/book2skills-ch1.json
```

Print the required ingest schema:

```bash
cd backend
uv run python scripts/book2skills_agent.py schema
```

Print the required knowledge-unit ingest schema:

```bash
cd backend
uv run python scripts/book2skills_agent.py knowledge-unit-schema
```

Ingest comprehensive book-level knowledge units:

```bash
cd backend
uv run python scripts/book2skills_agent.py ingest-knowledge-units <book_id> /tmp/book-kus.json
```

Ingest an agent-generated skill:

```bash
cd backend
uv run python scripts/book2skills_agent.py ingest-skill <book_id> /tmp/agent-skill.json
```

## MCP

Install the optional MCP extra before running the server:

```bash
cd backend
uv sync --extra mcp
```

Example local MCP config:

```json
{
  "mcpServers": {
    "book2skills": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "backend/scripts/book2skills_mcp_server.py"
      ],
      "env": {
        "BOOK2SKILLS_API_BASE_URL": "http://localhost:8000"
      }
    }
  }
}
```

Available tools:

- `book2skills_list_books`
- `book2skills_upload_book`
- `book2skills_get_book`
- `book2skills_wait_book_ready`
- `book2skills_get_book_content`
- `book2skills_get_knowledge_unit_schema`
- `book2skills_get_agent_skill_schema`
- `book2skills_ingest_knowledge_units`
- `book2skills_ingest_agent_skill`

The MCP tools do not generate the skill. They expose parsed content and persist the final structured payload produced by the agent.

### Convert One Book To A Skill With MCP

Use this flow from an MCP-capable agent such as Codex or Claude Desktop after the Book2Skills backend is running.

1. Upload the book with `book2skills_upload_book`.

   Input:

   ```json
   {
     "path": "/absolute/path/to/book.pdf",
     "wait": true
   }
   ```

   Keep the returned `book_id`. If `wait` is `false`, call `book2skills_wait_book_ready` with that `book_id` before reading content.

2. Read the table of contents with `book2skills_get_book_content`.

   Input:

   ```json
   {
     "book_id": "<book_id>",
     "mode": "index"
   }
   ```

   Use the returned chapter list to plan comprehensive KU extraction. Prefer reading all chapters; use selected chapters only when the intended skill deliberately targets a subset of the book.

3. Read chapter bodies with `book2skills_get_book_content`.

   Input:

   ```json
   {
     "book_id": "<book_id>",
     "mode": "chapter",
     "chapter_num": 1
   }
   ```

   Repeat for the chapters needed to extract a comprehensive set of book-level KUs. Every agent-submitted KU must cite a `source_quote` copied from these chapter bodies.

4. Inspect the required KU payload schema with `book2skills_get_knowledge_unit_schema`.

   The schema is the contract for the next step. The agent should generate JSON matching the returned payload schema, not a hand-written schema copied from this document.

5. Ask the agent to produce the KU payload in its own context.

   Suggested prompt:

   ```text
   Use the Book2Skills MCP content already read from this book to extract comprehensive book-level knowledge units.

   Requirements:
   - Output JSON with generator_name and knowledge_units.
   - Each knowledge unit must be atomic and reusable across future collection/KG workflows.
   - Each knowledge unit must include source_chapter_num and a non-empty source_quote copied exactly from the book.
   - Do not only extract KUs for the final skill steps. Cover the book's important principles, methods, examples, and when_to_use guidance.
   - Do not invent citations. If source evidence is weak, read more chapters first.
   ```

   Example payload:

   ```json
   {
     "generator_name": "codex",
     "knowledge_units": [
       {
         "source_chapter_num": 1,
         "source_quote": "系统由一组相互连接的要素构成。",
         "principle": "分析系统时不能只看要素，还要看连接关系和目标。",
         "method": "系统思维",
         "step_by_step": ["识别要素", "识别连接关系", "识别系统目标"],
         "example": "局部效率提升可能降低整体效率。",
         "when_to_use": ["分析复杂问题", "判断局部优化是否有效"],
         "tags": ["系统思维", "复杂问题"]
       }
     ]
   }
   ```

6. Persist the KU payload with `book2skills_ingest_knowledge_units`.

   Input:

   ```json
   {
     "book_id": "<book_id>",
     "payload": {
       "generator_name": "codex",
       "knowledge_units": [
         {
           "source_chapter_num": 1,
           "source_quote": "...",
           "principle": "...",
           "method": "...",
           "step_by_step": ["..."],
           "example": "...",
           "when_to_use": ["..."],
           "tags": ["..."]
         }
       ]
     }
   }
   ```

7. Inspect the required skill payload schema with `book2skills_get_agent_skill_schema`.

   The schema is the contract for the next step. The agent should generate JSON matching `AgentSkillIngestRequest`, not free-form Markdown.

8. Ask the agent to produce the skill payload in its own context.

   Suggested prompt:

   ```text
   Use the Book2Skills MCP content already read from this book to create an agent skill payload.

   Requirements:
   - Output JSON matching book2skills_get_agent_skill_schema.
   - Create router_md plus one or more focused skills.
   - Each skill should be executable: clear when_to_use, concrete thinking_steps, and practical workflow language.
   - Every thinking_steps item must include a non-empty source_quote copied exactly from the book content and a source_chapter.
   - Do not invent citations. If evidence is weak, omit that step or read more chapters first.
   - Set metadata.generated_by to "agent" and metadata.agent_name to the current agent name.
   ```

9. Persist the generated payload with `book2skills_ingest_agent_skill`.

   Input:

   ```json
   {
     "book_id": "<book_id>",
     "payload": {
       "router_md": "...",
       "skills": [
         {
           "name": "...",
           "description": "...",
           "when_to_use": ["..."],
           "thinking_steps": [
             {
               "step_num": 1,
               "action": "...",
               "source_quote": "...",
               "source_chapter": "..."
             }
           ],
           "references_keywords": ["..."]
         }
       ],
       "metadata": {
         "generated_by": "agent",
         "agent_name": "codex"
       }
     }
   }
   ```

9. Open the existing Book2Skills web UI.

   The ingested skill package should appear as a ready skill for that book. It can be viewed, downloaded, and used through the same storage surfaces as skills generated by the built-in LLM pipeline.

Important boundaries:

- MCP does not make Book2Skills call an agent. The agent calls Book2Skills.
- Book2Skills stores book-level KUs before skill ingest, then stores the final skill payload, creates `SkillPackage` and `Skill` rows, and indexes skill vectors.
- The agent is responsible for reading enough source content and producing faithful, cited skill JSON.
- Agent skill ingest will fail until the book has knowledge units. Extract KUs comprehensively first; do not only extract KUs for the few steps used in the skill.

## Payload Example

```json
{
  "router_md": "# Agent 主调度指南\n\n根据用户目标选择合适技能。",
  "skills": [
    {
      "name": "Customer_Discovery",
      "description": "验证用户问题是否真实存在。",
      "when_to_use": ["需要判断一个问题是否值得做"],
      "thinking_steps": [
        {
          "step_num": 1,
          "action": "写下要验证的问题假设",
          "source_quote": "从 references 章节中摘录的一句原文",
          "source_chapter": "第 1 章"
        }
      ],
      "references_keywords": ["用户访谈", "问题验证"]
    }
  ],
  "metadata": {
    "generated_by": "agent",
    "agent_name": "codex"
  }
}
```

Every `thinking_steps[]` item must include a non-empty `source_quote` copied from book content.

## Storage

Agent-ingested skills are first-class Book2Skills skills:

- `book_knowledge_units` stores the authoritative book-level KU set.
- `skill_packages` stores the final `skill_md`, scripts, templates, and provenance.
- `skills` stores one row per modular skill.
- `skills_vectors` stores one vector per modular skill.
- `scripts.metadata.generated_by` is `agent`.
- `scripts.metadata.vector_index_status` is `indexed` or `error`.

## Troubleshooting

Book is not ready:

- `content` and `ingest-skill` require a ready book.
- Use `wait-ready <book_id>` or the MCP `book2skills_wait_book_ready` tool.

References are missing:

- The content endpoint reads `storage/{book_id}/references/`.
- Reprocess the book if `references/index.json` is missing.

Invalid skill payload:

- Run `schema` or `book2skills_get_agent_skill_schema`.
- Check that `skills` is non-empty.
- Check every step has `source_quote` and `source_chapter`.

Qdrant unavailable during ingest:

- The skill package still persists.
- `scripts.metadata.vector_index_status` becomes `error`.
- The skill can be viewed and downloaded, but vector search may not find it until reindexing is added.

Backend API base URL wrong:

- Set `BOOK2SKILLS_API_BASE_URL`, for example:

```bash
export BOOK2SKILLS_API_BASE_URL=http://localhost:8000
```

## Collection Skill Generation Through MCP

Collection generation remains server-side. Agent clients only orchestrate the existing Book2Skills APIs.

MCP workflow:

1. Use `book2skills_list_books` to find ready books.
2. Use `book2skills_create_collection` with two or more `book_ids`.
3. Use `book2skills_generate_collection_skill` with `wait=true`.
4. If the run enters `error` or is stale-generating, use `book2skills_retry_collection_skill` to create a fresh backend run.
5. Use `book2skills_pack_collection_skill` once the run is ready.
6. Use `book2skills_download_collection_skill` to save the zip locally.
7. Inspect the unpacked `scripts/` directory for:
   - `source_kus.json`
   - `ku_similarity_candidates.json`
   - `normalized_ku_groups.json`
   - `same_as_edges.json`
   - `deduped_view.json`

The agent must not generate collection skill content itself in this workflow. It can inspect artifacts and report quality signals, such as zero `same_as_edges` or overly broad themes.

CLI equivalent:

```bash
cd backend
uv run python -m app.agent_client.cli list-books
uv run python -m app.agent_client.cli create-collection --name "认知合集" BOOK_ID_A BOOK_ID_B
uv run python -m app.agent_client.cli generate-collection COLLECTION_ID --goal "提炼跨书方法论" --wait
uv run python -m app.agent_client.cli pack-collection-skill RUN_ID
uv run python -m app.agent_client.cli download-collection-skill RUN_ID /absolute/path/skills.zip
# Optional retry:
uv run python -m app.agent_client.cli retry-collection-skill RUN_ID --goal "换个目标"
```
