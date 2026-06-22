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
