import uuid
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.api.routes.collection_skills import (
    _build_collection_skill_response,
    _ensure_packable_collection_skill,
)
from app.models.models import Collection, CollectionSkillPackage


def make_package(status: str = "ready", skill_md: str | None = "# Skill") -> CollectionSkillPackage:
    collection = Collection(
        id=uuid.uuid4(),
        name="产品方法论合集",
        status="active",
        created_at=datetime(2026, 6, 18),
        updated_at=datetime(2026, 6, 18),
    )
    return CollectionSkillPackage(
        id=uuid.uuid4(),
        collection_id=collection.id,
        collection=collection,
        skill_md=skill_md,
        scripts=None,
        templates=None,
        zip_path=None,
        version=1,
        status=status,
        created_at=datetime(2026, 6, 18),
        updated_at=datetime(2026, 6, 18),
    )


def test_build_collection_skill_response():
    package = make_package()

    response = _build_collection_skill_response(package)

    assert response.id == package.id
    assert response.collection_id == package.collection_id
    assert response.status == "ready"


def test_ensure_packable_collection_skill_rejects_non_ready():
    package = make_package(status="draft")

    with pytest.raises(HTTPException) as exc:
        _ensure_packable_collection_skill(package)

    assert exc.value.status_code == 400
    assert "尚未就绪" in exc.value.detail


def test_ensure_packable_collection_skill_rejects_empty_skill_md():
    package = make_package(status="ready", skill_md="")

    with pytest.raises(HTTPException) as exc:
        _ensure_packable_collection_skill(package)

    assert exc.value.status_code == 400
    assert "SKILL.md" in exc.value.detail
