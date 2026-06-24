import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.agent_client.client import Book2SkillsAgentClient
from app.agent_client.types import AgentClientConfig
from app.schemas.schemas import AgentKnowledgeUnitIngestRequest, AgentSkillIngestRequest


def make_client() -> Book2SkillsAgentClient:
    return Book2SkillsAgentClient(
        AgentClientConfig(
            base_url=os.getenv("BOOK2SKILLS_API_BASE_URL", "http://localhost:8000"),
            token=os.getenv("BOOK2SKILLS_API_TOKEN") or None,
            timeout_seconds=float(os.getenv("BOOK2SKILLS_CLIENT_TIMEOUT_SECONDS", "120")),
        )
    )


def agent_skill_schema_payload() -> dict[str, Any]:
    return {
        "payload_schema": AgentSkillIngestRequest.model_json_schema(),
        "instructions": [
            "Read book content through the content command or MCP tool.",
            "Generate structured skills; do not return only markdown.",
            "Every thinking step must include a non-empty source_quote from the book content.",
            "Call ingest-skill with the completed JSON payload.",
        ],
    }


def knowledge_unit_schema_payload() -> dict[str, Any]:
    return {
        "payload_schema": AgentKnowledgeUnitIngestRequest.model_json_schema(),
        "instructions": [
            "Read all relevant book chapters before creating this payload.",
            "Accumulate book-level knowledge units and submit them once per book.",
            "Every knowledge unit must include a non-empty source_quote copied from the book content.",
            "source_chapter_num must refer to a chapter returned by the content index.",
        ],
    }


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _print_pretty_books(books: list[dict]) -> None:
    for book in books:
        book_id = book.get("book_id") or book.get("id") or "-"
        title = book.get("title") or "Untitled"
        status = book.get("status") or "-"
        print(f"{book_id}\t{status}\t{title}")


def _print_pretty_mapping(data: dict) -> None:
    for key, value in data.items():
        print(f"{key}: {value}")


def _read_json_payload(path: str) -> dict:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("Payload must be a JSON object")
    return payload


def _read_payload(path: str) -> dict:
    payload = _read_json_payload(path)
    if "skills" not in payload:
        raise SystemExit("Payload must include a top-level 'skills' field")
    try:
        AgentSkillIngestRequest.model_validate(payload)
    except ValidationError as exc:
        raise SystemExit(str(exc)) from exc
    return payload


def _read_knowledge_units_payload(path: str) -> dict:
    payload = _read_json_payload(path)
    try:
        AgentKnowledgeUnitIngestRequest.model_validate(payload)
    except ValidationError as exc:
        raise SystemExit(str(exc)) from exc
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book2skills-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-books")
    list_parser.add_argument("--format", choices=["pretty", "json"], default="pretty")

    upload_parser = subparsers.add_parser("upload")
    upload_parser.add_argument("path", type=Path)
    upload_parser.add_argument("--title")
    upload_parser.add_argument("--wait", action="store_true")
    upload_parser.add_argument("--format", choices=["pretty", "json"], default="pretty")

    wait_parser = subparsers.add_parser("wait-ready")
    wait_parser.add_argument("book_id")
    wait_parser.add_argument("--timeout", type=int, default=1800)
    wait_parser.add_argument("--interval", type=int, default=5)

    content_parser = subparsers.add_parser("content")
    content_parser.add_argument("book_id")
    content_parser.add_argument("--mode", choices=["index", "chapter", "full"], default="index")
    content_parser.add_argument("--chapter-num", type=int)
    content_parser.add_argument("--output", type=Path)

    subparsers.add_parser("schema")
    subparsers.add_parser("knowledge-unit-schema")

    ingest_parser = subparsers.add_parser("ingest-skill")
    ingest_parser.add_argument("book_id")
    ingest_parser.add_argument("payload_json")

    ku_parser = subparsers.add_parser("ingest-knowledge-units", help="Persist book-level knowledge units")
    ku_parser.add_argument("book_id")
    ku_parser.add_argument("payload", help="Path to KU JSON payload, or '-' for stdin")
    ku_parser.add_argument("--format", choices=["pretty", "json"], default="pretty")

    list_collections_parser = subparsers.add_parser("list-collections")
    list_collections_parser.add_argument("--format", choices=["pretty", "json"], default="pretty")

    create_collection_parser = subparsers.add_parser("create-collection")
    create_collection_parser.add_argument("--name", required=True)
    create_collection_parser.add_argument("--description")
    create_collection_parser.add_argument("book_ids", nargs="+")

    get_collection_parser = subparsers.add_parser("get-collection")
    get_collection_parser.add_argument("collection_id")

    generate_collection_parser = subparsers.add_parser("generate-collection")
    generate_collection_parser.add_argument("collection_id")
    generate_collection_parser.add_argument("--goal")
    generate_collection_parser.add_argument("--no-detect-conflicts", action="store_true")
    generate_collection_parser.add_argument("--wait", action="store_true")
    generate_collection_parser.add_argument("--timeout", type=int, default=3600)
    generate_collection_parser.add_argument("--interval", type=int, default=5)

    collection_runs_parser = subparsers.add_parser("list-collection-runs")
    collection_runs_parser.add_argument("collection_id")
    collection_runs_parser.add_argument("--format", choices=["pretty", "json"], default="pretty")

    collection_skill_parser = subparsers.add_parser("get-collection-skill")
    collection_skill_parser.add_argument("skill_id")

    wait_collection_skill_parser = subparsers.add_parser("wait-collection-skill")
    wait_collection_skill_parser.add_argument("skill_id")
    wait_collection_skill_parser.add_argument("--timeout", type=int, default=3600)
    wait_collection_skill_parser.add_argument("--interval", type=int, default=5)

    pack_collection_skill_parser = subparsers.add_parser("pack-collection-skill")
    pack_collection_skill_parser.add_argument("skill_id")

    retry_collection_skill_parser = subparsers.add_parser("retry-collection-skill")
    retry_collection_skill_parser.add_argument("skill_id")
    retry_collection_skill_parser.add_argument("--goal")
    retry_collection_skill_parser.add_argument("--no-detect-conflicts", action="store_true")

    download_collection_skill_parser = subparsers.add_parser("download-collection-skill")
    download_collection_skill_parser.add_argument("skill_id")
    download_collection_skill_parser.add_argument("output", type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "schema":
        _print_json(agent_skill_schema_payload())
        return 0

    if args.command == "knowledge-unit-schema":
        _print_json(knowledge_unit_schema_payload())
        return 0

    client = make_client()
    try:
        if args.command == "list-books":
            books = client.list_books()
            if args.format == "json":
                _print_json(books)
            else:
                _print_pretty_books(books)
            return 0

        if args.command == "upload":
            if args.title:
                print(
                    "Warning: --title is currently ignored by the Book2Skills upload API.",
                    file=sys.stderr,
                )
            result = client.upload_book(args.path, title=args.title)
            book_id = result.get("book_id") or result.get("id")
            if args.wait and book_id:
                result = client.wait_ready(book_id)
            if args.format == "json":
                _print_json(result)
            else:
                _print_pretty_mapping(result)
            return 0

        if args.command == "wait-ready":
            _print_json(
                client.wait_ready(
                    args.book_id,
                    timeout_seconds=args.timeout,
                    interval_seconds=args.interval,
                )
            )
            return 0

        if args.command == "content":
            result = client.get_content(args.book_id, mode=args.mode, chapter_num=args.chapter_num)
            if args.output:
                args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                _print_json(result)
            return 0

        if args.command == "ingest-skill":
            payload = _read_payload(args.payload_json)
            result = client.ingest_skill(args.book_id, payload)
            _print_json(
                {
                    "skill_package_id": result.get("id"),
                    "status": result.get("status"),
                    "skill_count": len(payload.get("skills", [])),
                    "response": result,
                }
            )
            return 0

        if args.command == "ingest-knowledge-units":
            payload = _read_knowledge_units_payload(args.payload)
            result = client.ingest_knowledge_units(args.book_id, payload)
            if args.format == "json":
                _print_json(result)
            else:
                _print_pretty_mapping(result)
            return 0

        if args.command == "list-collections":
            collections = client.list_collections()
            if args.format == "json":
                _print_json(collections)
            else:
                for collection in collections:
                    print(
                        f"{collection.get('id')}\t{collection.get('book_count', '-')}\t"
                        f"{collection.get('status', '-')}\t{collection.get('name')}"
                    )
            return 0

        if args.command == "create-collection":
            if len(args.book_ids) < 2:
                raise SystemExit("create-collection requires at least two book ids")
            result = client.create_collection(
                name=args.name,
                description=args.description,
                book_ids=args.book_ids,
            )
            _print_json(result)
            return 0

        if args.command == "get-collection":
            _print_json(client.get_collection(args.collection_id))
            return 0

        if args.command == "generate-collection":
            result = client.generate_collection_skill(
                args.collection_id,
                user_goal=args.goal,
                reuse_extracted_kus=True,
                detect_conflicts=not args.no_detect_conflicts,
            )
            if args.wait and result.get("id"):
                result = client.wait_collection_skill_ready(
                    result["id"],
                    timeout_seconds=args.timeout,
                    interval_seconds=args.interval,
                )
            _print_json(result)
            return 0

        if args.command == "list-collection-runs":
            runs = client.list_collection_skills(args.collection_id)
            if args.format == "json":
                _print_json(runs)
            else:
                for run in runs:
                    print(
                        f"{run.get('id')}\t{run.get('status')}\t"
                        f"{run.get('pipeline_phase', '-')}\t{run.get('created_at', '-')}"
                    )
            return 0

        if args.command == "get-collection-skill":
            _print_json(client.get_collection_skill(args.skill_id))
            return 0

        if args.command == "wait-collection-skill":
            _print_json(
                client.wait_collection_skill_ready(
                    args.skill_id,
                    timeout_seconds=args.timeout,
                    interval_seconds=args.interval,
                )
            )
            return 0

        if args.command == "pack-collection-skill":
            _print_json(client.pack_collection_skill(args.skill_id))
            return 0

        if args.command == "retry-collection-skill":
            _print_json(
                client.retry_collection_skill(
                    args.skill_id,
                    user_goal=args.goal,
                    detect_conflicts=not args.no_detect_conflicts,
                )
            )
            return 0

        if args.command == "download-collection-skill":
            result = client.download_collection_skill(args.skill_id, args.output)
            _print_json(result)
            return 0
    finally:
        close = getattr(client, "close", None)
        if close:
            close()

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
