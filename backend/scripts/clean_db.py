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


def _clean_path_if_exists(path: Path) -> None:
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


def _book_storage_dir(book_id: str) -> Path:
    return Path(settings.STORAGE_LOCAL_PATH) / book_id


def _collection_storage_dir(collection_id: str) -> Path:
    return Path(settings.STORAGE_LOCAL_PATH) / "collections" / collection_id


def _find_invalidated_collection_ids(book_id: str, rows) -> set[str]:
    counts: dict[str, int] = {}
    containing: set[str] = set()
    for row in rows:
        collection_id = str(row.collection_id)
        row_book_id = str(row.book_id)
        counts[collection_id] = counts.get(collection_id, 0) + 1
        if row_book_id == book_id:
            containing.add(collection_id)
    return {collection_id for collection_id in containing if counts.get(collection_id, 0) - 1 < 2}


async def clean_all_data() -> None:
    engine = create_async_engine(str(settings.DATABASE_URL))
    async with engine.begin() as conn:
        print("Truncating PostgreSQL tables...")
        await conn.execute(text("TRUNCATE TABLE conversations CASCADE;"))
        await conn.execute(text("TRUNCATE TABLE skills CASCADE;"))
        await conn.execute(text("TRUNCATE TABLE skill_packages CASCADE;"))
        await conn.execute(text("TRUNCATE TABLE collection_skill_packages CASCADE;"))
        await conn.execute(text("TRUNCATE TABLE collection_books CASCADE;"))
        await conn.execute(text("TRUNCATE TABLE collections CASCADE;"))
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
    invalidated_collection_ids: set[str] = set()

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

        collection_rows_result = await conn.execute(
            text("SELECT collection_id, book_id FROM collection_books")
        )
        invalidated_collection_ids = _find_invalidated_collection_ids(str(book.id), collection_rows_result.fetchall())
        if invalidated_collection_ids:
            print("Collections that will also be deleted because they would have fewer than 2 books:")
            for collection_id in sorted(invalidated_collection_ids):
                print(f"- {collection_id}")

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
        if invalidated_collection_ids:
            await conn.execute(
                text("DELETE FROM collection_skill_packages WHERE collection_id = ANY(CAST(:collection_ids AS uuid[]))"),
                {"collection_ids": list(invalidated_collection_ids)},
            )
            await conn.execute(
                text(
                    """
                    DELETE FROM collection_books
                    WHERE book_id = :book_id
                       OR collection_id = ANY(CAST(:collection_ids AS uuid[]))
                    """
                ),
                {"book_id": str(book.id), "collection_ids": list(invalidated_collection_ids)},
            )
            await conn.execute(
                text("DELETE FROM collections WHERE id = ANY(CAST(:collection_ids AS uuid[]))"),
                {"collection_ids": list(invalidated_collection_ids)},
            )
        else:
            await conn.execute(
                text("DELETE FROM collection_books WHERE book_id = :book_id"),
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

    _clean_path_if_exists(_book_storage_dir(str(book.id)))
    for collection_id in invalidated_collection_ids:
        _clean_path_if_exists(_collection_storage_dir(collection_id))

    print("\n✅ Selected book cleaned successfully.")


async def clean_single_collection() -> None:
    engine = create_async_engine(str(settings.DATABASE_URL))
    collection = None

    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT id, name, description, created_at
                FROM collections
                ORDER BY created_at DESC
                """
            )
        )
        collections = result.fetchall()

        if not collections:
            print("No collections found in database.")
            await engine.dispose()
            return

        print("\nAvailable collections:")
        for idx, row in enumerate(collections, start=1):
            print(f"{idx}. {row.name} ({row.id})")

        raw = input("\nSelect one collection to clean by number (or q to quit): ").strip().lower()
        if raw in {"q", "quit", "exit"}:
            print("Cancelled.")
            await engine.dispose()
            return
        if not raw.isdigit():
            print("Invalid selection. Please input a number.")
            await engine.dispose()
            return

        selected_index = int(raw)
        if selected_index < 1 or selected_index > len(collections):
            print("Selection out of range.")
            await engine.dispose()
            return

        collection = collections[selected_index - 1]
        print(f"\nSelected: {collection.name} ({collection.id})")
        if not _confirm("Continue cleaning this collection and its generated skill packages? Source books stay"):
            print("Cancelled.")
            await engine.dispose()
            return

        await conn.execute(
            text("DELETE FROM collection_skill_packages WHERE collection_id = :collection_id"),
            {"collection_id": str(collection.id)},
        )
        await conn.execute(
            text("DELETE FROM collection_books WHERE collection_id = :collection_id"),
            {"collection_id": str(collection.id)},
        )
        await conn.execute(
            text("DELETE FROM collections WHERE id = :collection_id"),
            {"collection_id": str(collection.id)},
        )
        print("PostgreSQL rows for selected collection deleted.")

    await engine.dispose()

    _clean_path_if_exists(_collection_storage_dir(str(collection.id)))
    print("\n✅ Selected collection cleaned successfully.")


async def main() -> None:
    print("Choose cleanup mode:")
    print("1. Clean ALL data (truncate all)")
    print("2. Clean ONE selected book")
    print("3. Clean ONE selected collection")
    mode = input("Input 1, 2, or 3 (default 2): ").strip() or "2"

    if mode == "1":
        if not _confirm("This will delete ALL data. Continue"):
            print("Cancelled.")
            return
        await clean_all_data()
        return

    if mode == "2":
        await clean_single_book()
        return

    if mode == "3":
        await clean_single_collection()
        return

    print("Unknown mode. Exit.")


if __name__ == "__main__":
    asyncio.run(main())
