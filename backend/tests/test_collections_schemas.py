import uuid

import pytest
from pydantic import ValidationError

from app.schemas.schemas import CollectionCreateRequest, CollectionUpdateRequest


def test_collection_create_requires_two_unique_books():
    book_id = uuid.uuid4()

    with pytest.raises(ValidationError):
        CollectionCreateRequest(name="产品方法论", book_ids=[book_id])

    with pytest.raises(ValidationError):
        CollectionCreateRequest(name="产品方法论", book_ids=[book_id, book_id])


def test_collection_create_rejects_blank_name():
    with pytest.raises(ValidationError):
        CollectionCreateRequest(
            name="   ",
            book_ids=[uuid.uuid4(), uuid.uuid4()],
        )


def test_collection_update_allows_partial_metadata():
    request = CollectionUpdateRequest(description="用于产品 discovery 的书单")

    assert request.name is None
    assert request.description == "用于产品 discovery 的书单"
    assert request.book_ids is None


def test_collection_update_validates_book_ids_when_present():
    book_id = uuid.uuid4()

    with pytest.raises(ValidationError):
        CollectionUpdateRequest(book_ids=[book_id])
