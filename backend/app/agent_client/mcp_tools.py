from pathlib import Path
from typing import Literal

from app.agent_client.cli import agent_skill_schema_payload
from app.agent_client.client import Book2SkillsAgentClient


def list_books_tool(client: Book2SkillsAgentClient) -> dict:
    return {"books": client.list_books()}


def upload_book_tool(
    client: Book2SkillsAgentClient,
    path: str,
    title: str | None = None,
    wait: bool = False,
    timeout_seconds: int = 1800,
    interval_seconds: int = 5,
) -> dict:
    book_path = Path(path)
    if not book_path.is_absolute():
        raise ValueError("path must be absolute")
    if not book_path.exists():
        raise FileNotFoundError(book_path)
    if book_path.is_dir():
        raise IsADirectoryError(book_path)

    result = client.upload_book(book_path, title=title)
    book_id = result.get("book_id") or result.get("id")
    if wait and book_id:
        return client.wait_ready(
            book_id,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        )
    return result


def get_book_tool(client: Book2SkillsAgentClient, book_id: str) -> dict:
    return client.get_book(book_id)


def wait_book_ready_tool(
    client: Book2SkillsAgentClient,
    book_id: str,
    timeout_seconds: int = 1800,
    interval_seconds: int = 5,
) -> dict:
    return client.wait_ready(
        book_id,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
    )


def get_book_content_tool(
    client: Book2SkillsAgentClient,
    book_id: str,
    mode: Literal["index", "chapter", "full"] = "index",
    chapter_num: int | None = None,
) -> dict:
    if mode == "chapter" and chapter_num is None:
        raise ValueError("chapter_num is required when mode='chapter'")
    return client.get_content(book_id, mode=mode, chapter_num=chapter_num)


def get_agent_skill_schema_tool() -> dict:
    return agent_skill_schema_payload()


def ingest_agent_skill_tool(
    client: Book2SkillsAgentClient,
    book_id: str,
    payload: dict,
) -> dict:
    return client.ingest_skill(book_id, payload)
