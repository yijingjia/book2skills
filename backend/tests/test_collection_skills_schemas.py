import uuid
from datetime import datetime

from app.schemas.schemas import CollectionSkillPackageResponse


def test_collection_skill_package_response_shape():
    skill_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    created = datetime(2026, 6, 18)

    response = CollectionSkillPackageResponse(
        id=skill_id,
        collection_id=collection_id,
        skill_md=None,
        scripts=None,
        templates=None,
        zip_path=None,
        version=1,
        status="draft",
        created_at=created,
        updated_at=created,
    )

    assert response.id == skill_id
    assert response.collection_id == collection_id
    assert response.status == "draft"
    assert response.version == 1
