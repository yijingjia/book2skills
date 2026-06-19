import uuid
from datetime import UTC, datetime, timedelta

from app.api.routes.collections import (
    _build_collection_skill_list_item,
    _is_retryable_collection_skill,
)
from app.models.models import CollectionSkillPackage


def make_package(status: str = "ready") -> CollectionSkillPackage:
    return CollectionSkillPackage(
        id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        status=status,
        scripts=None,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_build_collection_skill_list_item_reads_phase_and_failed_reason():
    package = CollectionSkillPackage(
        id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        status="error",
        scripts={
            "pipeline_phase": "failed_at_skill_modules_ready",
            "failed_reason": "quota exhausted",
        },
        version=1,
        created_at=datetime(2026, 6, 19, 1, 0, 0),
        updated_at=datetime(2026, 6, 19, 1, 1, 0),
    )

    item = _build_collection_skill_list_item(package)

    assert item.status == "error"
    assert item.pipeline_phase == "failed_at_skill_modules_ready"
    assert item.failed_reason == "quota exhausted"
    assert item.is_retryable is True


def test_build_collection_skill_list_item_handles_empty_scripts():
    package = CollectionSkillPackage(
        id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        status="generating",
        scripts=None,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    item = _build_collection_skill_list_item(package)

    assert item.pipeline_phase is None
    assert item.failed_reason is None
    assert item.is_retryable is False


def test_retryable_collection_skill_accepts_error_package():
    package = make_package(status="error")

    assert _is_retryable_collection_skill(package) is True


def test_retryable_collection_skill_rejects_ready_package():
    package = make_package(status="ready")

    assert _is_retryable_collection_skill(package) is False


def test_retryable_collection_skill_accepts_stale_generating_package():
    package = make_package(status="generating")
    package.created_at = datetime.now(UTC) - timedelta(minutes=31)

    assert _is_retryable_collection_skill(package) is True
