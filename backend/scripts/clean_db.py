# docker exec -it book2skills-backend env PYTHONPATH=. python scripts/clean_db.py

import asyncio
import shutil
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


def _confirm(message: str) -> bool:
    answer = input(f"{message} [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _is_within_storage(path: Path) -> bool:
    storage_root = Path(settings.STORAGE_LOCAL_PATH).resolve()
    target = path.resolve()
    try:
        target.relative_to(storage_root)
        return True
    except ValueError:
        return False


def _clean_file_if_exists(file_path: str | None) -> None:
    if not file_path:
        return
    path = Path(file_path)
    if not _is_within_storage(path):
        print(f"Skip unsafe path outside storage root: {path}")
        return
    if path.exists():
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            print(f"Deleted local path: {path}")
        except Exception as e:
            print(f"Failed to delete local path {path}: {e}")


async def clean_all_data() -> None:
    engine = create_async_engine(str(settings.DATABASE_URL))
    async with engine.begin() as conn:
        print("Truncating PostgreSQL tables...")
        await conn.execute(text("TRUNCATE TABLE conversations CASCADE;"))
        await conn.execute(text("TRUNCATE TABLE skills CASCADE;"))
        await conn.execute(text("TRUNCATE TABLE skill_packages CASCADE;"))
        await conn.execute(text("TRUNCATE TABLE chapters CASCADE;"))
        await conn.execute(text("TRUNCATE TABLE books CASCADE;"))
        print("PostgreSQL tables truncated.")
    await engine.dispose()

    try:
        from qdrant_client import QdrantClient

        qdrant = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
        collections = qdrant.get_collections().collections
        for col in collections:
            qdrant.delete_collection(col.name)
            print(f"Deleted Qdrant collection: {col.name}")
        print("Qdrant collections cleaned.")
    except Exception as e:
        print(f"Qdrant cleanup skipped or failed: {e}")

    try:
        storage_path = Path(settings.STORAGE_LOCAL_PATH)
        if storage_path.exists():
            print(f"Cleaning contents of {storage_path}...")
            for item in storage_path.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            print(f"Local storage cleaned: {storage_path}")
        else:
            print(f"Storage path does not exist, skipping: {storage_path}")
    except Exception as e:
        print(f"Local storage cleanup failed: {e}")

    print("\n✅ All data cleaned successfully.")


async def clean_single_book() -> None:
    engine = create_async_engine(str(settings.DATABASE_URL))
    book = None
    skill_package_paths: list[str] = []

    async with engine.begin() as conn:
        books_result = await conn.execute(
            text(
                """
                SELECT id, title, author, file_path, created_at
                FROM books
                ORDER BY created_at DESC
                """
            )
        )
        books = books_result.fetchall()

        if not books:
            print("No books found in database.")
            await engine.dispose()
            return

        print("\nAvailable books:")
        for idx, row in enumerate(books, start=1):
            display_title = row.title or "(untitled)"
            display_author = row.author or "(unknown author)"
            print(f"{idx}. {display_title} - {display_author} ({row.id})")

        raw = input("\nSelect one book to clean by number (or q to quit): ").strip().lower()
        if raw in {"q", "quit", "exit"}:
            print("Cancelled.")
            await engine.dispose()
            return
        if not raw.isdigit():
            print("Invalid selection. Please input a number.")
            await engine.dispose()
            return

        selected_index = int(raw)
        if selected_index < 1 or selected_index > len(books):
            print("Selection out of range.")
            await engine.dispose()
            return

        book = books[selected_index - 1]
        print(f"\nSelected: {book.title or '(untitled)'} ({book.id})")
        if not _confirm("Continue cleaning this single book and its related data?"):
            print("Cancelled.")
            await engine.dispose()
            return

        skill_path_result = await conn.execute(
            text(
                """
                SELECT zip_path
                FROM skill_packages
                WHERE book_id = :book_id
                """
            ),
            {"book_id": str(book.id)},
        )
        skill_package_paths = [r.zip_path for r in skill_path_result.fetchall() if r.zip_path]

        await conn.execute(
            text(
                """
                DELETE FROM conversations
                WHERE skill_package_id IN (
                    SELECT id FROM skill_packages WHERE book_id = :book_id
                )
                """
            ),
            {"book_id": str(book.id)},
        )
        await conn.execute(
            text(
                """
                DELETE FROM skills
                WHERE book_id = :book_id
                   OR skill_package_id IN (
                        SELECT id FROM skill_packages WHERE book_id = :book_id
                   )
                """
            ),
            {"book_id": str(book.id)},
        )
        await conn.execute(
            text("DELETE FROM skill_packages WHERE book_id = :book_id"),
            {"book_id": str(book.id)},
        )
        await conn.execute(
            text("DELETE FROM chapters WHERE book_id = :book_id"),
            {"book_id": str(book.id)},
        )
        await conn.execute(
            text("DELETE FROM books WHERE id = :book_id"),
            {"book_id": str(book.id)},
        )
        print("PostgreSQL rows for selected book deleted.")

    await engine.dispose()

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        qdrant = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
        collection_name = str(book.id)
        existing = {c.name for c in qdrant.get_collections().collections}
        if collection_name in existing:
            qdrant.delete_collection(collection_name)
            print(f"Deleted Qdrant collection: {collection_name}")
        else:
            print(f"No Qdrant collection found for book: {collection_name}")

        skills_collection = "skills_vectors"
        if skills_collection in existing:
            qdrant.delete(
                collection_name=skills_collection,
                points_selector=Filter(
                    must=[FieldCondition(key="book_id", match=MatchValue(value=str(book.id)))]
                ),
            )
            print(f"Deleted vectors in {skills_collection} for book: {book.id}")
    except Exception as e:
        print(f"Qdrant cleanup skipped or failed: {e}")

    _clean_file_if_exists(book.file_path)
    for zip_path in skill_package_paths:
        _clean_file_if_exists(zip_path)

    print("\n✅ Selected book cleaned successfully.")


async def main() -> None:
    print("Choose cleanup mode:")
    print("1. Clean ALL data (truncate all)")
    print("2. Clean ONE selected book")
    mode = input("Input 1 or 2 (default 2): ").strip() or "2"

    if mode == "1":
        if not _confirm("This will delete ALL data. Continue"):
            print("Cancelled.")
            return
        await clean_all_data()
        return

    if mode == "2":
        await clean_single_book()
        return

    print("Unknown mode. Exit.")


if __name__ == "__main__":
    asyncio.run(main())
