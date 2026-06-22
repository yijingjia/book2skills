import uuid
from unittest.mock import AsyncMock, patch

from app.pipeline.skill_persistence import (
    _with_vector_index_status,
    build_agent_skill_markdown,
    build_agent_skill_scripts,
    build_skill_embedding_text,
    build_skill_model_kwargs,
    build_skill_vector_payload,
    persist_agent_skill_package,
)
from app.schemas.schemas import AgentSkillMetadata, ModularSkill, SkillStep


class FakeAsyncSession:
    def __init__(self, fail_on_add: bool = False):
        self.fail_on_add = fail_on_add
        self.added = []
        self.commit = AsyncMock()
        self.flush = AsyncMock(side_effect=self._flush)
        self.refresh = AsyncMock(side_effect=self._refresh)
        self.rollback = AsyncMock()

    def add(self, obj):
        if self.fail_on_add:
            raise RuntimeError("db insert failed")
        self.added.append(obj)

    async def _flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def _refresh(self, _obj):
        return None


class FakeEmbedder:
    async def aembed_documents(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


def make_skill(name: str = "Customer_Discovery") -> ModularSkill:
    return ModularSkill(
        name=name,
        description="Validate whether a customer problem is real.",
        when_to_use=["需要验证用户问题"],
        thinking_steps=[
            SkillStep(
                step_num=1,
                action="提出问题假设",
                source_quote="先确认问题是否真实存在。",
                source_chapter="第 1 章",
            )
        ],
        references_keywords=["customer discovery"],
    )


def test_build_agent_skill_markdown_combines_router_and_modules():
    markdown = build_agent_skill_markdown("# Router", [make_skill()])

    assert markdown.startswith("# Router")
    assert markdown.split("\n\n---\n\n")[0].strip() == "# Router"
    assert len(markdown.split("\n\n---\n\n")) == 2
    assert "Customer_Discovery" in markdown
    assert "提出问题假设" in markdown


def test_build_agent_skill_scripts_records_metadata_and_module_files():
    scripts = build_agent_skill_scripts(
        router_md="# Router",
        skills=[make_skill()],
        extra_scripts={"notes.json": {"ok": True}},
        metadata=AgentSkillMetadata(agent_name="codex"),
    )

    assert scripts["metadata"]["generated_by"] == "agent"
    assert scripts["metadata"]["agent_name"] == "codex"
    assert scripts["metadata"]["vector_index_status"] == "pending"
    assert scripts["agent_ingest_report.json"]["generated_modules"] == 1
    assert any(key.startswith("skill_0_Customer_Discovery") for key in scripts)


def test_build_skill_embedding_text_contains_core_routing_fields():
    text = build_skill_embedding_text(make_skill())

    assert "技能名: Customer_Discovery" in text
    assert "适用场景" in text
    assert "提出问题假设" in text


def test_build_skill_vector_payload_marks_agent_source():
    book_id = uuid.uuid4()
    package_id = uuid.uuid4()
    skill_id = uuid.uuid4()

    payload = build_skill_vector_payload(
        book_id=book_id,
        skill_package_id=package_id,
        skill_id=skill_id,
        skill=make_skill(),
    )

    assert payload["book_id"] == str(book_id)
    assert payload["skill_package_id"] == str(package_id)
    assert payload["skill_id"] == str(skill_id)
    assert payload["generated_by"] == "agent"


def test_build_skill_model_kwargs_maps_modular_skill_to_skill_columns():
    book_id = uuid.uuid4()
    package_id = uuid.uuid4()
    skill_id = uuid.uuid4()
    skill = make_skill()

    kwargs = build_skill_model_kwargs(
        skill_id=skill_id,
        book_id=book_id,
        skill_package_id=package_id,
        skill=skill,
    )

    assert kwargs["id"] == skill_id
    assert kwargs["book_id"] == book_id
    assert kwargs["skill_package_id"] == package_id
    assert kwargs["name"] == "Customer_Discovery"
    assert kwargs["workflow"][0]["action"] == "提出问题假设"
    assert kwargs["templates"] == {}


def test_with_vector_index_status_records_success_and_error():
    scripts = {"metadata": {"generated_by": "agent"}}

    indexed = _with_vector_index_status(scripts, "indexed")
    assert indexed["metadata"]["generated_by"] == "agent"
    assert indexed["metadata"]["vector_index_status"] == "indexed"
    assert "vector_index_error" not in indexed["metadata"]

    errored = _with_vector_index_status(indexed, "error", "qdrant unavailable")
    assert errored["metadata"]["vector_index_status"] == "error"
    assert "qdrant unavailable" in errored["metadata"]["vector_index_error"]


async def test_persist_agent_skill_package_marks_indexed_on_success():
    db = FakeAsyncSession()

    with (
        patch("app.pipeline.skill_persistence.get_embedding_client", return_value=FakeEmbedder()),
        patch("app.pipeline.skill_persistence.close_embedding_client", new=AsyncMock()),
        patch("app.pipeline.skill_persistence.QdrantClient"),
        patch("app.pipeline.skill_persistence._upsert_skill_vectors", new=AsyncMock()) as upsert,
    ):
        package = await persist_agent_skill_package(
            db=db,
            book_id=uuid.uuid4(),
            router_md="# Router",
            skills=[make_skill()],
            scripts={},
            templates=None,
            metadata=AgentSkillMetadata(agent_name="codex"),
        )

    assert package.status == "ready"
    assert package.scripts["metadata"]["vector_index_status"] == "indexed"
    assert len(db.added) == 2
    assert db.commit.await_count == 2
    upsert.assert_awaited_once()
    db.rollback.assert_not_awaited()


async def test_persist_agent_skill_package_keeps_package_when_qdrant_fails():
    db = FakeAsyncSession()

    with (
        patch("app.pipeline.skill_persistence.get_embedding_client", return_value=FakeEmbedder()),
        patch("app.pipeline.skill_persistence.close_embedding_client", new=AsyncMock()),
        patch("app.pipeline.skill_persistence.QdrantClient"),
        patch(
            "app.pipeline.skill_persistence._upsert_skill_vectors",
            new=AsyncMock(side_effect=RuntimeError("qdrant down")),
        ),
    ):
        package = await persist_agent_skill_package(
            db=db,
            book_id=uuid.uuid4(),
            router_md="# Router",
            skills=[make_skill()],
            scripts={},
            templates=None,
            metadata=AgentSkillMetadata(agent_name="codex"),
        )

    assert package.status == "ready"
    assert package.scripts["metadata"]["vector_index_status"] == "error"
    assert "qdrant down" in package.scripts["metadata"]["vector_index_error"]
    assert len(db.added) == 2
    assert db.commit.await_count == 2
    db.rollback.assert_not_awaited()


async def test_persist_agent_skill_package_rolls_back_on_db_error():
    db = FakeAsyncSession(fail_on_add=True)

    with (
        patch("app.pipeline.skill_persistence.get_embedding_client", return_value=FakeEmbedder()),
        patch("app.pipeline.skill_persistence.close_embedding_client", new=AsyncMock()),
        patch("app.pipeline.skill_persistence.QdrantClient"),
        patch("app.pipeline.skill_persistence._upsert_skill_vectors", new=AsyncMock()) as upsert,
    ):
        try:
            await persist_agent_skill_package(
                db=db,
                book_id=uuid.uuid4(),
                router_md="# Router",
                skills=[make_skill()],
                scripts={},
                templates=None,
                metadata=AgentSkillMetadata(agent_name="codex"),
            )
        except RuntimeError as exc:
            assert "db insert failed" in str(exc)
        else:
            raise AssertionError("Expected DB error to propagate")

    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
    upsert.assert_not_awaited()
