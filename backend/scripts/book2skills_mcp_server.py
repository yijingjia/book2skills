"""MCP server wrapper for Book2Skills agent tools."""
# ruff: noqa: E402,I001

from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent_client.cli import make_client  # noqa: E402
from app.agent_client.mcp_tools import (  # noqa: E402
    create_collection_tool,
    download_collection_skill_tool,
    generate_collection_skill_tool,
    get_agent_skill_schema_tool,
    get_book_content_tool,
    get_book_tool,
    get_collection_skill_tool,
    get_collection_tool,
    get_knowledge_unit_schema_tool,
    ingest_agent_skill_tool,
    ingest_knowledge_units_tool,
    list_collection_skills_tool,
    list_collections_tool,
    list_books_tool,
    pack_collection_skill_tool,
    retry_collection_skill_tool,
    upload_book_tool,
    wait_book_ready_tool,
    wait_collection_skill_ready_tool,
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
def book2skills_get_knowledge_unit_schema() -> dict:
    """Return the structured payload schema for comprehensive book-level knowledge units."""
    return get_knowledge_unit_schema_tool()


@mcp.tool()
def book2skills_ingest_agent_skill(book_id: str, payload: dict) -> dict:
    """Persist a fully generated structured agent skill payload into Book2Skills."""
    client = _client()
    try:
        return ingest_agent_skill_tool(client, book_id=book_id, payload=payload)
    finally:
        client.close()


@mcp.tool()
def book2skills_ingest_knowledge_units(book_id: str, payload: dict) -> dict:
    """Persist comprehensive book-level knowledge units before ingesting a skill."""
    client = _client()
    try:
        return ingest_knowledge_units_tool(client, book_id=book_id, payload=payload)
    finally:
        client.close()


@mcp.tool()
def book2skills_list_collections() -> dict:
    """List Book2Skills collections."""
    client = _client()
    try:
        return list_collections_tool(client)
    finally:
        client.close()


@mcp.tool()
def book2skills_create_collection(
    name: str,
    book_ids: list[str],
    description: str | None = None,
) -> dict:
    """Create a collection from two or more existing Book2Skills book ids."""
    client = _client()
    try:
        return create_collection_tool(
            client,
            name=name,
            book_ids=book_ids,
            description=description,
        )
    finally:
        client.close()


@mcp.tool()
def book2skills_get_collection(collection_id: str) -> dict:
    """Get collection metadata and member books."""
    client = _client()
    try:
        return get_collection_tool(client, collection_id=collection_id)
    finally:
        client.close()


@mcp.tool()
def book2skills_generate_collection_skill(
    collection_id: str,
    user_goal: str | None = None,
    detect_conflicts: bool = True,
    wait: bool = False,
    timeout_seconds: int = 3600,
    interval_seconds: int = 5,
) -> dict:
    """Trigger backend collection skill generation; optionally wait for ready status."""
    client = _client()
    try:
        return generate_collection_skill_tool(
            client,
            collection_id=collection_id,
            user_goal=user_goal,
            detect_conflicts=detect_conflicts,
            wait=wait,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        )
    finally:
        client.close()


@mcp.tool()
def book2skills_list_collection_skills(collection_id: str) -> dict:
    """List generation runs for one collection."""
    client = _client()
    try:
        return list_collection_skills_tool(client, collection_id=collection_id)
    finally:
        client.close()


@mcp.tool()
def book2skills_get_collection_skill(skill_id: str) -> dict:
    """Get one collection skill generation run/package."""
    client = _client()
    try:
        return get_collection_skill_tool(client, skill_id=skill_id)
    finally:
        client.close()


@mcp.tool()
def book2skills_wait_collection_skill_ready(
    skill_id: str,
    timeout_seconds: int = 3600,
    interval_seconds: int = 5,
) -> dict:
    """Poll a collection skill run until it is ready."""
    client = _client()
    try:
        return wait_collection_skill_ready_tool(
            client,
            skill_id=skill_id,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        )
    finally:
        client.close()


@mcp.tool()
def book2skills_pack_collection_skill(skill_id: str) -> dict:
    """Pack a ready collection skill into a downloadable zip."""
    client = _client()
    try:
        return pack_collection_skill_tool(client, skill_id=skill_id)
    finally:
        client.close()


@mcp.tool()
def book2skills_retry_collection_skill(
    skill_id: str,
    user_goal: str | None = None,
    detect_conflicts: bool = True,
) -> dict:
    """Retry an error or stale collection skill run by creating a fresh backend run."""
    client = _client()
    try:
        return retry_collection_skill_tool(
            client,
            skill_id=skill_id,
            user_goal=user_goal,
            detect_conflicts=detect_conflicts,
        )
    finally:
        client.close()


@mcp.tool()
def book2skills_download_collection_skill(skill_id: str, output_path: str) -> dict:
    """Download a packed collection skill zip to an absolute local path."""
    client = _client()
    try:
        return download_collection_skill_tool(
            client,
            skill_id=skill_id,
            output_path=output_path,
        )
    finally:
        client.close()


if __name__ == "__main__":
    mcp.run()
