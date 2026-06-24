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
