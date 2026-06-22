"""Thin script wrapper for the Book2Skills agent CLI."""
# ruff: noqa: E402,I001

from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent_client.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
