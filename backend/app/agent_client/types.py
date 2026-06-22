from pydantic import BaseModel, Field, field_validator


class AgentClientConfig(BaseModel):
    base_url: str = "http://localhost:8000"
    token: str | None = None
    timeout_seconds: float = 120

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, v: str) -> str:
        return v.rstrip("/")


class UploadedBook(BaseModel):
    id: str | None = None
    book_id: str | None = None
    title: str | None = None
    status: str | None = None

    @property
    def resolved_id(self) -> str | None:
        return self.id or self.book_id


class BookListItem(BaseModel):
    id: str | None = None
    book_id: str | None = None
    title: str | None = None
    author: str | None = None
    status: str
    extra: dict = Field(default_factory=dict)

    model_config = {"extra": "allow"}
