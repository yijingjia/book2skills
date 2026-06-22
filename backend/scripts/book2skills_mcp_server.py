"""MCP server wrapper for Book2Skills agent tools."""
# ruff: noqa: E402,I001

from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent_client.cli import make_client  # noqa: E402
from app.agent_client.mcp_tools import (  # noqa: E402
    get_agent_skill_schema_tool,
    get_book_content_tool,
    get_book_tool,
    ingest_agent_skill_tool,
    list_books_tool,
    upload_book_tool,
    wait_book_ready_tool,
)


try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError as exc:
    raise SystemExit(
        "The Python MCP SDK is not installed. Install it with: cd backend && uv sync --extra mcp"
    ) from exc


mcp = FastMCP("book2skills")


def _client():
    return make_client()


@mcp.tool()
def book2skills_list_books() -> dict:
    """List books known to Book2Skills."""
    client = _client()
    try:
        return list_books_tool(client)
    finally:
        client.close()


@mcp.tool()
def book2skills_upload_book(path: str, title: str | None = None, wait: bool = False) -> dict:
    """Upload a local PDF/EPUB into Book2Skills; optionally wait until processing is ready."""
    client = _client()
    try:
        return upload_book_tool(client, path=path, title=title, wait=wait)
    finally:
        client.close()


@mcp.tool()
def book2skills_get_book(book_id: str) -> dict:
    """Get processing status and metadata for one book."""
    client = _client()
    try:
        return get_book_tool(client, book_id=book_id)
    finally:
        client.close()


@mcp.tool()
def book2skills_wait_book_ready(
    book_id: str,
    timeout_seconds: int = 1800,
    interval_seconds: int = 5,
) -> dict:
    """Poll a book until the existing parse/embed pipeline marks it ready."""
    client = _client()
    try:
        return wait_book_ready_tool(
            client,
            book_id=book_id,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        )
    finally:
        client.close()


@mcp.tool()
def book2skills_get_book_content(
    book_id: str,
    mode: str = "index",
    chapter_num: int | None = None,
) -> dict:
    """Read parsed book content for local agent-side skill generation."""
    client = _client()
    try:
        return get_book_content_tool(
            client,
            book_id=book_id,
            mode=mode,  # type: ignore[arg-type]
            chapter_num=chapter_num,
        )
    finally:
        client.close()


@mcp.tool()
def book2skills_get_agent_skill_schema() -> dict:
    """Return the structured payload schema agents must produce before ingest."""
    return get_agent_skill_schema_tool()


@mcp.tool()
def book2skills_ingest_agent_skill(book_id: str, payload: dict) -> dict:
    """Persist a fully generated structured agent skill payload into Book2Skills."""
    client = _client()
    try:
        return ingest_agent_skill_tool(client, book_id=book_id, payload=payload)
    finally:
        client.close()


if __name__ == "__main__":
    mcp.run()
