---
name: book2skills-generator
description: Use when the user asks to generate a Book2Skills skill from a local PDF/EPUB/book path, convert a book into a skill, or says "用 Book2Skills 把某本书生成 skill". This skill drives the Book2Skills MCP workflow: upload or reuse a book, read parsed content, extract comprehensive book-level knowledge units, ingest KUs, generate a structured agent skill payload, and ingest the final skill.
---

# Book2Skills Generator

Use Book2Skills MCP tools to turn a local book into a first-class Book2Skills skill package.

The backend is the source of truth for schemas. Do not hardcode KU or skill payload structures from memory. Always fetch schemas at runtime.

## Workflow

1. Upload or reuse the book.
   - If the user gives a local path, call `book2skills_upload_book(path, wait=true)`.
   - If the user gives a `book_id`, skip upload and call `book2skills_get_book`.
   - If the user gives only a title or book name, call `book2skills_list_books` first and look for an exact or obvious title match. Reuse the existing `book_id` when one clear match exists.
   - If multiple existing books match, ask the user which one to use. If no existing book matches, ask for a local path before uploading.
   - If the book is not ready, call `book2skills_wait_book_ready`.

2. Read the book content.
   - Call `book2skills_get_book_content(book_id, mode="index")`.
   - Use the chapter list as the coverage checklist.
   - Read chapters with `book2skills_get_book_content(book_id, mode="chapter", chapter_num=N)`.
   - Prefer reading every chapter. Read selected chapters only when the user explicitly asks for a narrow skill.

3. Fetch the KU schema.
   - Call `book2skills_get_knowledge_unit_schema()`.
   - Follow the returned schema exactly.

4. Extract comprehensive book-level KUs.
   - Extract from the whole book, not just the final skill steps.
   - Cover important principles, methods, procedures, examples, and usage conditions.
   - Every KU must include a non-empty `source_quote` copied exactly from the book content.
   - Every KU must include a valid `source_chapter_num` from the content index.
   - Do not invent content that is not grounded in the book.

5. Self-check KU coverage before ingest.
   - Compare extracted KUs with the content index.
   - Confirm each chapter was read and considered.
   - If a chapter has no KU, note why in your private reasoning before continuing.
   - Because KU ingest is replace-by-book, accumulate all KUs in memory and call `book2skills_ingest_knowledge_units` exactly once for the whole book.

6. Ingest KUs.
   - Call `book2skills_ingest_knowledge_units(book_id, payload)`.
   - Continue only after the ingest succeeds.

7. Fetch the skill schema.
   - Call `book2skills_get_agent_skill_schema()`.
   - Follow the returned schema exactly.

8. Generate the skill payload.
   - Create `router_md` and one or more focused skill modules.
   - Make the skill executable, not a reading note.
   - Each module needs clear `name`, `description`, `when_to_use`, and concrete thinking steps.
   - Every thinking step must include a non-empty `source_quote` copied exactly from the book content and a source chapter.
   - Keep claims faithful to the book; do not blend in outside knowledge unless the user explicitly asks.

9. Ingest the skill.
   - Call `book2skills_ingest_agent_skill(book_id, payload)`.

10. Report only the useful result.
   - Include `book_id`, `skill_package_id`, KU count, skill module count, status, and any warning.

## Important Constraints

- Do not call `book2skills_ingest_knowledge_units` once per chapter. It replaces all KUs for the book.
- Do not write schema examples into final payload from this file. Fetch schemas through MCP.
- Do not skip KU ingestion. Agent skill ingest requires existing book-level KUs.
- If content cannot be read, stop and report the failing tool and book id.
- If references/storage appear missing, stop and report the error instead of producing an uncited skill.
