from pathlib import Path
from typing import Literal

from app.agent_client.cli import agent_skill_schema_payload, knowledge_unit_schema_payload
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


def get_knowledge_unit_schema_tool() -> dict:
    return knowledge_unit_schema_payload()


def ingest_agent_skill_tool(
    client: Book2SkillsAgentClient,
    book_id: str,
    payload: dict,
) -> dict:
    return client.ingest_skill(book_id, payload)


def ingest_knowledge_units_tool(
    client: Book2SkillsAgentClient,
    book_id: str,
    payload: dict,
) -> dict:
    return client.ingest_knowledge_units(book_id, payload)


def list_collections_tool(client: Book2SkillsAgentClient) -> dict:
    return {"collections": client.list_collections()}


def create_collection_tool(
    client: Book2SkillsAgentClient,
    name: str,
    book_ids: list[str],
    description: str | None = None,
) -> dict:
    if len(book_ids) < 2:
        raise ValueError("collection requires at least two books")
    if len(set(book_ids)) != len(book_ids):
        raise ValueError("book_ids must be unique")
    return client.create_collection(name=name, book_ids=book_ids, description=description)


def get_collection_tool(client: Book2SkillsAgentClient, collection_id: str) -> dict:
    return client.get_collection(collection_id)


def generate_collection_skill_tool(
    client: Book2SkillsAgentClient,
    collection_id: str,
    user_goal: str | None = None,
    detect_conflicts: bool = True,
    wait: bool = False,
    timeout_seconds: int = 3600,
    interval_seconds: int = 5,
) -> dict:
    result = client.generate_collection_skill(
        collection_id,
        user_goal=user_goal,
        reuse_extracted_kus=True,
        detect_conflicts=detect_conflicts,
    )
    skill_id = result.get("id")
    if wait and skill_id:
        return client.wait_collection_skill_ready(
            skill_id,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        )
    return result


def list_collection_skills_tool(client: Book2SkillsAgentClient, collection_id: str) -> dict:
    return {"runs": client.list_collection_skills(collection_id)}


def get_collection_skill_tool(client: Book2SkillsAgentClient, skill_id: str) -> dict:
    return client.get_collection_skill(skill_id)


def wait_collection_skill_ready_tool(
    client: Book2SkillsAgentClient,
    skill_id: str,
    timeout_seconds: int = 3600,
    interval_seconds: int = 5,
) -> dict:
    return client.wait_collection_skill_ready(
        skill_id,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
    )


def pack_collection_skill_tool(client: Book2SkillsAgentClient, skill_id: str) -> dict:
    return client.pack_collection_skill(skill_id)


def retry_collection_skill_tool(
    client: Book2SkillsAgentClient,
    skill_id: str,
    user_goal: str | None = None,
    detect_conflicts: bool = True,
) -> dict:
    return client.retry_collection_skill(
        skill_id,
        user_goal=user_goal,
        detect_conflicts=detect_conflicts,
    )


def download_collection_skill_tool(
    client: Book2SkillsAgentClient,
    skill_id: str,
    output_path: str,
) -> dict:
    path = Path(output_path)
    if not path.is_absolute():
        raise ValueError("output_path must be absolute")
    if path.exists() and path.is_dir():
        raise IsADirectoryError(path)
    return client.download_collection_skill(skill_id, path)
