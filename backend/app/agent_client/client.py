import time
from pathlib import Path
from typing import Literal

import httpx

from app.agent_client.types import AgentClientConfig


class Book2SkillsClientError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        endpoint: str | None = None,
        body: str | None = None,
    ):
        details = message
        if status_code is not None:
            details += f" status={status_code}"
        if endpoint:
            details += f" endpoint={endpoint}"
        if body:
            details += f" body={body[:500]}"
        super().__init__(details)
        self.status_code = status_code
        self.endpoint = endpoint
        self.body = body


class Book2SkillsAgentClient:
    def __init__(
        self,
        config: AgentClientConfig | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.config = config or AgentClientConfig()
        headers = {}
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        self._client = httpx.Client(
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
            headers=headers,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, endpoint: str, **kwargs) -> dict | list:
        response = self._client.request(method, endpoint, **kwargs)
        if response.status_code >= 400:
            raise Book2SkillsClientError(
                "Book2Skills API request failed",
                status_code=response.status_code,
                endpoint=endpoint,
                body=response.text,
            )
        if not response.content:
            return {}
        return response.json()

    def list_books(self) -> list[dict]:
        result = self._request("GET", "/api/books")
        return list(result) if isinstance(result, list) else []

    def upload_book(self, path: Path, title: str | None = None) -> dict:
        if not path.exists():
            raise FileNotFoundError(path)
        if path.is_dir():
            raise IsADirectoryError(path)

        data = {}
        if title:
            data["title"] = title
        with path.open("rb") as file_obj:
            files = {"file": (path.name, file_obj)}
            result = self._request("POST", "/api/books/upload", files=files, data=data or None)
        return dict(result)

    def get_book(self, book_id: str) -> dict:
        return dict(self._request("GET", f"/api/books/{book_id}/status"))

    def wait_ready(
        self,
        book_id: str,
        timeout_seconds: int = 1800,
        interval_seconds: int = 5,
    ) -> dict:
        deadline = time.monotonic() + timeout_seconds
        while True:
            status = self.get_book(book_id)
            if status.get("status") == "ready":
                return status
            if status.get("status") == "error":
                raise Book2SkillsClientError(
                    "Book processing failed",
                    body=status.get("error_message") or str(status),
                )
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for book {book_id} to be ready")
            if interval_seconds > 0:
                time.sleep(interval_seconds)

    def get_content(
        self,
        book_id: str,
        mode: Literal["index", "chapter", "full"] = "index",
        chapter_num: int | None = None,
    ) -> dict:
        params: dict[str, str | int] = {"mode": mode}
        if chapter_num is not None:
            params["chapter_num"] = chapter_num
        return dict(self._request("GET", f"/api/books/{book_id}/content", params=params))

    def ingest_skill(self, book_id: str, payload: dict) -> dict:
        return dict(self._request("POST", f"/api/books/{book_id}/skills", json=payload))

    def ingest_knowledge_units(self, book_id: str, payload: dict) -> dict:
        return dict(self._request("POST", f"/api/books/{book_id}/knowledge-units", json=payload))
