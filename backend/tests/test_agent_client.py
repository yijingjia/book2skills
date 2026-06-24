import json

import httpx
import pytest

from app.agent_client.client import Book2SkillsAgentClient, Book2SkillsClientError
from app.agent_client.types import AgentClientConfig


def make_client(handler, **config_overrides):
    transport = httpx.MockTransport(handler)
    config = AgentClientConfig(**config_overrides)
    return Book2SkillsAgentClient(config=config, transport=transport)


def test_base_url_is_normalized_and_token_header_is_sent():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json=[])

    client = make_client(
        handler,
        base_url="http://example.test/",
        token="secret-token",
    )

    assert client.list_books() == []
    assert seen["url"] == "http://example.test/api/books"
    assert seen["authorization"] == "Bearer secret-token"


def test_get_content_sends_mode_and_chapter_params():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"mode": "chapter"})

    client = make_client(handler)

    result = client.get_content("book-1", mode="chapter", chapter_num=2)

    assert result == {"mode": "chapter"}
    assert seen["url"] == "http://localhost:8000/api/books/book-1/content?mode=chapter&chapter_num=2"


def test_wait_ready_returns_ready_status(monkeypatch):
    statuses = iter([
        {"status": "processing"},
        {"status": "ready", "book_id": "book-1"},
    ])
    client = make_client(lambda _request: httpx.Response(200, json={}))
    monkeypatch.setattr(client, "get_book", lambda _book_id: next(statuses))

    result = client.wait_ready("book-1", timeout_seconds=1, interval_seconds=0)

    assert result["status"] == "ready"


def test_wait_ready_fails_fast_on_error(monkeypatch):
    client = make_client(lambda _request: httpx.Response(200, json={}))
    monkeypatch.setattr(client, "get_book", lambda _book_id: {"status": "error", "error_message": "bad parse"})

    with pytest.raises(Book2SkillsClientError) as exc:
        client.wait_ready("book-1", timeout_seconds=1, interval_seconds=0)

    assert "bad parse" in str(exc.value)


def test_wait_ready_times_out(monkeypatch):
    client = make_client(lambda _request: httpx.Response(200, json={}))
    monkeypatch.setattr(client, "get_book", lambda _book_id: {"status": "processing"})

    with pytest.raises(TimeoutError):
        client.wait_ready("book-1", timeout_seconds=0, interval_seconds=0)


def test_ingest_skill_posts_payload_unchanged():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["payload"] = request.read()
        return httpx.Response(200, json={"id": "pkg-1", "status": "ready"})

    client = make_client(handler)
    payload = {"router_md": "# Router", "skills": [{"name": "Skill"}]}

    result = client.ingest_skill("book-1", payload)

    assert result["id"] == "pkg-1"
    assert seen["url"] == "http://localhost:8000/api/books/book-1/skills"
    assert b'"router_md":"# Router"' in seen["payload"]


def test_ingest_knowledge_units_posts_payload_unchanged():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["payload"] = request.content
        return httpx.Response(200, json={"knowledge_units_count": 1})

    client = make_client(handler)
    payload = {"knowledge_units": [{"source_chapter_num": 1, "source_quote": "原文", "principle": "原则"}]}

    result = client.ingest_knowledge_units("book-1", payload)

    assert result == {"knowledge_units_count": 1}
    assert seen["url"] == "http://localhost:8000/api/books/book-1/knowledge-units"
    assert json.loads(seen["payload"]) == payload


def test_upload_book_posts_multipart_file(tmp_path):
    seen = {}
    book = tmp_path / "book.pdf"
    book.write_bytes(b"fake-pdf")

    def handler(request):
        seen["url"] = str(request.url)
        seen["content_type"] = request.headers.get("content-type")
        seen["body"] = request.read()
        return httpx.Response(200, json={"book_id": "book-1"})

    client = make_client(handler)

    result = client.upload_book(book)

    assert result == {"book_id": "book-1"}
    assert seen["url"] == "http://localhost:8000/api/books/upload"
    assert seen["content_type"].startswith("multipart/form-data")
    assert b'name="file"; filename="book.pdf"' in seen["body"]
    assert b"fake-pdf" in seen["body"]


def test_upload_book_rejects_missing_path(tmp_path):
    client = make_client(lambda _request: httpx.Response(200, json={}))

    with pytest.raises(FileNotFoundError):
        client.upload_book(tmp_path / "missing.pdf")


def test_upload_book_rejects_directory(tmp_path):
    client = make_client(lambda _request: httpx.Response(200, json={}))

    with pytest.raises(IsADirectoryError):
        client.upload_book(tmp_path)


def test_http_error_includes_status_endpoint_and_body():
    def handler(_request):
        return httpx.Response(400, text="bad request")

    client = make_client(handler)

    with pytest.raises(Book2SkillsClientError) as exc:
        client.list_books()

    message = str(exc.value)
    assert "400" in message
    assert "/api/books" in message
    assert "bad request" in message


def test_collection_client_methods_call_existing_api_routes():
    import json

    import httpx

    from app.agent_client.client import Book2SkillsAgentClient
    from app.agent_client.types import AgentClientConfig

    seen: list[tuple[str, str, dict | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8")) if request.content else None
        seen.append((request.method, request.url.path, body))
        if request.method == "GET" and request.url.path == "/api/collections":
            return httpx.Response(200, json=[{"id": "collection-1", "name": "产品书单"}])
        if request.method == "POST" and request.url.path == "/api/collections":
            return httpx.Response(200, json={"id": "collection-1", "name": body["name"], "books": []})
        if request.method == "GET" and request.url.path == "/api/collections/collection-1":
            return httpx.Response(200, json={"id": "collection-1", "name": "产品书单", "books": []})
        if request.method == "POST" and request.url.path == "/api/collections/collection-1/generate":
            return httpx.Response(200, json={"id": "run-1", "collection_id": "collection-1", "status": "generating"})
        if request.method == "GET" and request.url.path == "/api/collections/collection-1/skills":
            return httpx.Response(200, json=[{"id": "run-1", "collection_id": "collection-1", "status": "ready"}])
        if request.method == "GET" and request.url.path == "/api/collection-skills/run-1":
            return httpx.Response(200, json={"id": "run-1", "collection_id": "collection-1", "status": "ready"})
        if request.method == "POST" and request.url.path == "/api/collection-skills/run-1/pack":
            return httpx.Response(200, json={"skill_package_id": "run-1", "zip_path": "/tmp/skills.zip"})
        if request.method == "POST" and request.url.path == "/api/collection-skills/run-1/retry":
            return httpx.Response(200, json={"id": "run-2", "collection_id": "collection-1", "status": "generating"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    client = Book2SkillsAgentClient(
        AgentClientConfig(base_url="http://testserver"),
        transport=httpx.MockTransport(handler),
    )

    assert client.list_collections()[0]["id"] == "collection-1"
    assert client.create_collection("产品书单", ["book-a", "book-b"], description="两本产品书")["id"] == "collection-1"
    assert client.get_collection("collection-1")["id"] == "collection-1"
    assert client.generate_collection_skill("collection-1", user_goal="提炼产品方法论")["status"] == "generating"
    assert client.list_collection_skills("collection-1")[0]["status"] == "ready"
    assert client.get_collection_skill("run-1")["status"] == "ready"
    assert client.pack_collection_skill("run-1")["zip_path"] == "/tmp/skills.zip"
    assert client.retry_collection_skill("run-1", user_goal="换个目标")["id"] == "run-2"

    assert ("POST", "/api/collections", {"name": "产品书单", "description": "两本产品书", "book_ids": ["book-a", "book-b"]}) in seen
    assert (
        "POST",
        "/api/collections/collection-1/generate",
        {
            "user_goal": "提炼产品方法论",
            "reuse_extracted_kus": True,
            "detect_conflicts": True,
        },
    ) in seen
    assert (
        "POST",
        "/api/collection-skills/run-1/retry",
        {
            "user_goal": "换个目标",
            "detect_conflicts": True,
        },
    ) in seen


def test_download_collection_skill_writes_zip_bytes(tmp_path):
    import httpx

    from app.agent_client.client import Book2SkillsAgentClient
    from app.agent_client.types import AgentClientConfig

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/collection-skills/run-1/download"
        return httpx.Response(200, content=b"zip-bytes", headers={"content-type": "application/zip"})

    output = tmp_path / "skills.zip"
    client = Book2SkillsAgentClient(
        AgentClientConfig(base_url="http://testserver"),
        transport=httpx.MockTransport(handler),
    )

    result = client.download_collection_skill("run-1", output)

    assert result == {"path": str(output), "bytes": 9}
    assert output.read_bytes() == b"zip-bytes"


def test_wait_collection_skill_ready_polls_until_ready():
    import httpx

    from app.agent_client.client import Book2SkillsAgentClient
    from app.agent_client.types import AgentClientConfig

    statuses = iter(["generating", "ready"])

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/collection-skills/run-1"
        return httpx.Response(200, json={"id": "run-1", "status": next(statuses)})

    client = Book2SkillsAgentClient(
        AgentClientConfig(base_url="http://testserver"),
        transport=httpx.MockTransport(handler),
    )

    result = client.wait_collection_skill_ready("run-1", timeout_seconds=5, interval_seconds=0)

    assert result["status"] == "ready"

