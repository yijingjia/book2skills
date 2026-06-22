import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.agent_client import cli


class FakeClient:
    def __init__(self):
        self.calls = []

    def list_books(self):
        self.calls.append(("list_books",))
        return [{"book_id": "book-1", "title": "Book", "status": "ready"}]

    def upload_book(self, path: Path, title=None):
        self.calls.append(("upload_book", path, title))
        return {"book_id": "book-1", "status": "pending"}

    def wait_ready(self, book_id: str, timeout_seconds=1800, interval_seconds=5):
        self.calls.append(("wait_ready", book_id, timeout_seconds, interval_seconds))
        return {"book_id": book_id, "status": "ready"}

    def get_content(self, book_id: str, mode="index", chapter_num=None):
        self.calls.append(("get_content", book_id, mode, chapter_num))
        return {"book_id": book_id, "mode": mode, "chapter_num": chapter_num}

    def ingest_skill(self, book_id: str, payload: dict):
        self.calls.append(("ingest_skill", book_id, payload))
        return {"id": "pkg-1", "status": "ready", "scripts": {}, "skill_md": "# Router"}


def valid_skill_payload():
    return {
        "router_md": "# Router",
        "skills": [
            {
                "name": "Customer_Discovery",
                "description": "Validate a real problem.",
                "when_to_use": ["需要验证问题"],
                "thinking_steps": [
                    {
                        "step_num": 1,
                        "action": "提出问题假设",
                        "source_quote": "先确认问题是否真实存在。",
                        "source_chapter": "第 1 章",
                    }
                ],
                "references_keywords": ["customer discovery"],
            }
        ],
    }


def run_cli(args, monkeypatch, capsys, fake=None, stdin=None):
    fake = fake or FakeClient()
    monkeypatch.setattr(cli, "make_client", lambda: fake)
    if stdin is not None:
        monkeypatch.setattr("sys.stdin", stdin)
    exit_code = cli.main(args)
    captured = capsys.readouterr()
    return exit_code, captured, fake


def test_list_books_outputs_json(monkeypatch, capsys):
    exit_code, captured, fake = run_cli(["list-books", "--format", "json"], monkeypatch, capsys)

    assert exit_code == 0
    assert json.loads(captured.out)[0]["book_id"] == "book-1"
    assert fake.calls == [("list_books",)]


def test_upload_wait_calls_upload_then_wait(tmp_path, monkeypatch, capsys):
    book = tmp_path / "book.pdf"
    book.write_text("pdf", encoding="utf-8")

    exit_code, _captured, fake = run_cli(["upload", str(book), "--wait"], monkeypatch, capsys)

    assert exit_code == 0
    assert fake.calls == [
        ("upload_book", book, None),
        ("wait_ready", "book-1", 1800, 5),
    ]


def test_upload_pretty_output_is_human_readable(tmp_path, monkeypatch, capsys):
    book = tmp_path / "book.pdf"
    book.write_text("pdf", encoding="utf-8")

    exit_code, captured, _fake = run_cli(["upload", str(book)], monkeypatch, capsys)

    assert exit_code == 0
    assert "book_id: book-1" in captured.out
    assert "status: pending" in captured.out


def test_upload_title_prints_warning(tmp_path, monkeypatch, capsys):
    book = tmp_path / "book.pdf"
    book.write_text("pdf", encoding="utf-8")

    exit_code, captured, _fake = run_cli(["upload", str(book), "--title", "Ignored"], monkeypatch, capsys)

    assert exit_code == 0
    assert "--title is currently ignored" in captured.err


def test_content_chapter_calls_client(monkeypatch, capsys):
    exit_code, captured, fake = run_cli(
        ["content", "book-1", "--mode", "chapter", "--chapter-num", "2"],
        monkeypatch,
        capsys,
    )

    assert exit_code == 0
    assert fake.calls == [("get_content", "book-1", "chapter", 2)]
    assert json.loads(captured.out)["chapter_num"] == 2


def test_schema_emits_agent_skill_ingest_schema(capsys):
    exit_code = cli.main(["schema"])
    captured = capsys.readouterr()

    payload = json.loads(captured.out)
    assert exit_code == 0
    assert "payload_schema" in payload
    assert "skills" in payload["payload_schema"]["properties"]


def test_ingest_skill_rejects_invalid_json(tmp_path, monkeypatch, capsys):
    payload_path = tmp_path / "bad.json"
    payload_path.write_text("{bad", encoding="utf-8")

    with pytest.raises(SystemExit):
        run_cli(["ingest-skill", "book-1", str(payload_path)], monkeypatch, capsys)


def test_ingest_skill_reads_stdin(monkeypatch, capsys):
    stdin = MagicMock()
    payload = valid_skill_payload()
    stdin.read.return_value = json.dumps(payload)

    exit_code, _captured, fake = run_cli(["ingest-skill", "book-1", "-"], monkeypatch, capsys, stdin=stdin)

    assert exit_code == 0
    assert fake.calls == [("ingest_skill", "book-1", payload)]
