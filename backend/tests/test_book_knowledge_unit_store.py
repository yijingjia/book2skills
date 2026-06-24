import uuid
from unittest.mock import AsyncMock

import pytest

from app.models.models import BookKnowledgeUnit
from app.pipeline.book_knowledge_unit_store import (
    book_ku_to_knowledge_unit,
    build_book_ku_row,
    knowledge_unit_to_content,
    replace_book_knowledge_units,
)
from app.schemas.schemas import KnowledgeUnit


class FakeAsyncSession:
    def __init__(self):
        self.executed = []
        self.added_all = []
        self.flush = AsyncMock()

    async def execute(self, statement):
        self.executed.append(statement)

    def add_all(self, rows):
        self.added_all.extend(rows)


def make_ku() -> KnowledgeUnit:
    return KnowledgeUnit(
        source_chunk_id="book_ch2_0",
        source_chapter_num=2,
        principle="局部最优不等于整体最优。",
        method="系统思维",
        step_by_step=["识别要素", "识别连接", "识别目标"],
        example="只提升单点效率会牺牲系统效率。",
        when_to_use=["分析复杂问题"],
    )


def test_knowledge_unit_to_content_keeps_semantic_fields():
    content = knowledge_unit_to_content(make_ku())

    assert content == {
        "principle": "局部最优不等于整体最优。",
        "method": "系统思维",
        "step_by_step": ["识别要素", "识别连接", "识别目标"],
        "example": "只提升单点效率会牺牲系统效率。",
        "when_to_use": ["分析复杂问题"],
    }


def test_build_book_ku_row_maps_provenance_and_content():
    book_id = uuid.uuid4()
    package_id = uuid.uuid4()

    row = build_book_ku_row(
        book_id=book_id,
        ku=make_ku(),
        source_quote="系统由要素、连接关系和目标构成。",
        generated_by="agent",
        generator_name="codex",
        skill_package_id=package_id,
        tags=["系统思维"],
    )

    assert row.book_id == book_id
    assert row.skill_package_id == package_id
    assert row.source_chunk_id == "book_ch2_0"
    assert row.source_chapter_num == 2
    assert row.source_quote == "系统由要素、连接关系和目标构成。"
    assert row.content["method"] == "系统思维"
    assert row.tags == ["系统思维"]
    assert row.generated_by == "agent"
    assert row.generator_name == "codex"


def test_build_book_ku_row_allows_missing_quote_for_llm_units():
    row = build_book_ku_row(
        book_id=uuid.uuid4(),
        ku=make_ku(),
        source_quote=None,
        generated_by="llm",
        generator_name=None,
        skill_package_id=uuid.uuid4(),
        tags=[],
    )

    assert row.source_quote is None
    assert row.generated_by == "llm"


@pytest.mark.asyncio
async def test_replace_book_knowledge_units_deletes_then_adds_rows():
    db = FakeAsyncSession()
    book_id = uuid.uuid4()

    rows = await replace_book_knowledge_units(
        db=db,
        book_id=book_id,
        units=[
            {
                "ku": make_ku(),
                "source_quote": "系统由要素、连接关系和目标构成。",
                "tags": ["系统思维"],
            }
        ],
        generated_by="agent",
        generator_name="codex",
        skill_package_id=None,
    )

    assert len(db.executed) == 1
    assert len(db.added_all) == 1
    assert rows == db.added_all
    assert db.added_all[0].book_id == book_id
    db.flush.assert_awaited_once()


def test_book_ku_to_knowledge_unit_restores_pipeline_schema():
    row = BookKnowledgeUnit(
        id=uuid.uuid4(),
        book_id=uuid.uuid4(),
        source_chunk_id="book_ch2_0",
        source_chapter_num=2,
        source_quote="系统由要素、连接关系和目标构成。",
        content=knowledge_unit_to_content(make_ku()),
        tags=["系统思维"],
        generated_by="agent",
        generator_name="codex",
    )

    ku = book_ku_to_knowledge_unit(row)

    assert ku.source_chunk_id == "book_ch2_0"
    assert ku.source_chapter_num == 2
    assert ku.method == "系统思维"
    assert ku.principle == "局部最优不等于整体最优。"
