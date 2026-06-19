from app.schemas.schemas import KnowledgeUnit


def _book_ids_for_kus(kus: list[KnowledgeUnit]) -> set[str]:
    book_ids: set[str] = set()
    for ku in kus:
        for source in ku.source_books or []:
            book_id = source.get("book_id")
            if book_id:
                book_ids.add(str(book_id))
        if ku.source_book_id:
            book_ids.add(str(ku.source_book_id))
    return book_ids


def build_consensus_artifacts(
    clustered_groups: list[tuple[str, str, list[KnowledgeUnit]]],
    total_books: int,
) -> list[dict]:
    artifacts = []
    denominator = max(total_books, 1)
    for theme_name, theme_description, kus in clustered_groups:
        book_ids = _book_ids_for_kus(kus)
        artifacts.append(
            {
                "theme": theme_name,
                "description": theme_description,
                "supporting_book_count": len(book_ids),
                "confidence": round(len(book_ids) / denominator, 2),
                "source_book_ids": sorted(book_ids),
            }
        )
    return sorted(artifacts, key=lambda item: item["supporting_book_count"], reverse=True)


def build_candidate_tension_artifacts(
    clustered_groups: list[tuple[str, str, list[KnowledgeUnit]]],
) -> list[dict]:
    artifacts = []
    for theme_name, theme_description, kus in clustered_groups:
        book_ids = _book_ids_for_kus(kus)
        methods = sorted({ku.method for ku in kus if ku.method})
        if len(book_ids) >= 2 and len(methods) >= 2:
            artifacts.append(
                {
                    "theme": theme_name,
                    "description": theme_description,
                    "source_book_ids": sorted(book_ids),
                    "variants": methods,
                }
            )
    return artifacts
