import json
from pathlib import Path

import pytest

from app.agent_client import mcp_tools


class FakeClient:
    def __init__(self):
        self.calls = []

    def list_books(self):
        self.calls.append(("list_books",))
        return [{"book_id": "book-1"}]

    def upload_book(self, path: Path, title=None):
        self.calls.append(("upload_book", path, title))
        return {"book_id": "book-1"}

    def get_book(self, book_id: str):
        self.calls.append(("get_book", book_id))
        return {"book_id": book_id, "status": "ready"}

    def wait_ready(self, book_id: str, timeout_seconds=1800, interval_seconds=5):
        self.calls.append(("wait_ready", book_id, timeout_seconds, interval_seconds))
        return {"book_id": book_id, "status": "ready"}

    def get_content(self, book_id: str, mode="index", chapter_num=None):
        self.calls.append(("get_content", book_id, mode, chapter_num))
        return {"book_id": book_id, "mode": mode, "chapter_num": chapter_num}

    def ingest_skill(self, book_id: str, payload: dict):
        self.calls.append(("ingest_skill", book_id, payload))
        return {"id": "pkg-1", "status": "ready"}

    def ingest_knowledge_units(self, book_id: str, payload: dict):
        self.calls.append(("ingest_knowledge_units", book_id, payload))
        return {"book_id": book_id, "knowledge_units_count": 1, "status": "ready"}

    def list_collections(self):
        self.calls.append(("list_collections",))
        return [{"id": "collection-1", "name": "认知合集"}]

    def create_collection(self, name: str, book_ids: list[str], description=None):
        self.calls.append(("create_collection", name, book_ids, description))
        return {"id": "collection-1", "name": name}

    def get_collection(self, collection_id: str):
        self.calls.append(("get_collection", collection_id))
        return {"id": collection_id, "name": "认知合集"}

    def generate_collection_skill(self, collection_id: str, user_goal=None, reuse_extracted_kus=True, detect_conflicts=True):
        self.calls.append(("generate_collection_skill", collection_id, user_goal, reuse_extracted_kus, detect_conflicts))
        return {"id": "run-1", "collection_id": collection_id, "status": "generating"}

    def list_collection_skills(self, collection_id: str):
        self.calls.append(("list_collection_skills", collection_id))
        return [{"id": "run-1", "status": "ready"}]

    def get_collection_skill(self, skill_id: str):
        self.calls.append(("get_collection_skill", skill_id))
        return {"id": skill_id, "status": "ready"}

    def wait_collection_skill_ready(self, skill_id: str, timeout_seconds=3600, interval_seconds=5):
        self.calls.append(("wait_collection_skill_ready", skill_id, timeout_seconds, interval_seconds))
        return {"id": skill_id, "status": "ready"}

    def pack_collection_skill(self, skill_id: str):
        self.calls.append(("pack_collection_skill", skill_id))
        return {"skill_package_id": skill_id, "zip_path": "/tmp/skills.zip"}

    def retry_collection_skill(self, skill_id: str, user_goal=None, detect_conflicts=True):
        self.calls.append(("retry_collection_skill", skill_id, user_goal, detect_conflicts))
        return {"id": "run-2", "collection_id": "collection-1", "status": "generating"}

    def download_collection_skill(self, skill_id: str, output_path: Path):
        self.calls.append(("download_collection_skill", skill_id, output_path))
        output_path.write_bytes(b"zip")
        return {"path": str(output_path), "bytes": 3}


def test_list_books_tool_calls_client():
    client = FakeClient()

    result = mcp_tools.list_books_tool(client)

    assert result == {"books": [{"book_id": "book-1"}]}
    assert client.calls == [("list_books",)]


def test_upload_book_tool_rejects_non_absolute_path():
    with pytest.raises(ValueError):
        mcp_tools.upload_book_tool(FakeClient(), "book.pdf")


def test_upload_book_tool_rejects_missing_file(tmp_path):
    missing = tmp_path / "missing.pdf"

    with pytest.raises(FileNotFoundError):
        mcp_tools.upload_book_tool(FakeClient(), str(missing))


def test_upload_book_tool_calls_client(tmp_path):
    book = tmp_path / "book.pdf"
    book.write_text("pdf", encoding="utf-8")
    client = FakeClient()

    result = mcp_tools.upload_book_tool(client, str(book), title="Book", wait=True)

    assert result["status"] == "ready"
    assert client.calls == [
        ("upload_book", book, "Book"),
        ("wait_ready", "book-1", 1800, 5),
    ]


def test_content_tool_requires_chapter_num_for_chapter_mode():
    with pytest.raises(ValueError):
        mcp_tools.get_book_content_tool(FakeClient(), "book-1", mode="chapter")


def test_content_tool_calls_client():
    client = FakeClient()

    result = mcp_tools.get_book_content_tool(client, "book-1", mode="chapter", chapter_num=2)

    assert result["chapter_num"] == 2
    assert client.calls == [("get_content", "book-1", "chapter", 2)]


def test_ingest_tool_passes_payload_unchanged():
    client = FakeClient()
    payload = {"router_md": "# Router", "skills": [{"name": "Skill"}]}

    result = mcp_tools.ingest_agent_skill_tool(client, "book-1", payload)

    assert result["id"] == "pkg-1"
    assert client.calls == [("ingest_skill", "book-1", payload)]


def test_ingest_knowledge_units_tool_passes_payload_unchanged():
    client = FakeClient()
    payload = {"knowledge_units": [{"source_chapter_num": 1, "source_quote": "原文", "principle": "原则"}]}

    result = mcp_tools.ingest_knowledge_units_tool(client, "book-1", payload)

    assert result["knowledge_units_count"] == 1
    assert client.calls == [("ingest_knowledge_units", "book-1", payload)]


def test_schema_tool_matches_cli_schema():
    result = mcp_tools.get_agent_skill_schema_tool()

    assert "payload_schema" in result
    assert "skills" in json.dumps(result["payload_schema"])


def test_knowledge_unit_schema_tool_matches_cli_schema():
    result = mcp_tools.get_knowledge_unit_schema_tool()

    assert "payload_schema" in result
    assert "knowledge_units" in json.dumps(result["payload_schema"])
    assert "source_quote" in json.dumps(result["payload_schema"])


def test_collection_tools_call_client(tmp_path):
    client = FakeClient()

    assert mcp_tools.list_collections_tool(client)["collections"][0]["id"] == "collection-1"
    assert mcp_tools.create_collection_tool(
        client,
        name="认知合集",
        book_ids=["book-a", "book-b"],
        description="两本书",
    )["id"] == "collection-1"
    assert mcp_tools.get_collection_tool(client, "collection-1")["id"] == "collection-1"
    assert mcp_tools.generate_collection_skill_tool(
        client,
        "collection-1",
        user_goal="提炼方法论",
        wait=True,
        timeout_seconds=10,
        interval_seconds=0,
    )["status"] == "ready"
    assert mcp_tools.list_collection_skills_tool(client, "collection-1")["runs"][0]["id"] == "run-1"
    assert mcp_tools.get_collection_skill_tool(client, "run-1")["status"] == "ready"
    assert mcp_tools.pack_collection_skill_tool(client, "run-1")["zip_path"] == "/tmp/skills.zip"
    assert mcp_tools.retry_collection_skill_tool(client, "run-1", user_goal="换个目标")["id"] == "run-2"

    output = tmp_path / "skills.zip"
    assert mcp_tools.download_collection_skill_tool(client, "run-1", str(output))["bytes"] == 3
    assert output.read_bytes() == b"zip"


def test_create_collection_tool_requires_two_unique_books():
    with pytest.raises(ValueError, match="at least two"):
        mcp_tools.create_collection_tool(FakeClient(), name="bad", book_ids=["book-a"])

    with pytest.raises(ValueError, match="unique"):
        mcp_tools.create_collection_tool(FakeClient(), name="bad", book_ids=["book-a", "book-a"])


def test_download_collection_skill_tool_requires_absolute_path(tmp_path):
    with pytest.raises(ValueError, match="absolute"):
        mcp_tools.download_collection_skill_tool(FakeClient(), "run-1", "skills.zip")

    with pytest.raises(IsADirectoryError):
        mcp_tools.download_collection_skill_tool(FakeClient(), "run-1", str(tmp_path))
