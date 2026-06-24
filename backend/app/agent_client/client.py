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

    def list_collections(self) -> list[dict]:
        result = self._request("GET", "/api/collections")
        return list(result) if isinstance(result, list) else []

    def create_collection(
        self,
        name: str,
        book_ids: list[str],
        description: str | None = None,
    ) -> dict:
        payload = {
            "name": name,
            "description": description,
            "book_ids": book_ids,
        }
        return dict(self._request("POST", "/api/collections", json=payload))

    def get_collection(self, collection_id: str) -> dict:
        return dict(self._request("GET", f"/api/collections/{collection_id}"))

    def generate_collection_skill(
        self,
        collection_id: str,
        *,
        user_goal: str | None = None,
        reuse_extracted_kus: bool = True,
        detect_conflicts: bool = True,
    ) -> dict:
        payload = {
            "user_goal": user_goal,
            "reuse_extracted_kus": reuse_extracted_kus,
            "detect_conflicts": detect_conflicts,
        }
        return dict(self._request("POST", f"/api/collections/{collection_id}/generate", json=payload))

    def list_collection_skills(self, collection_id: str) -> list[dict]:
        result = self._request("GET", f"/api/collections/{collection_id}/skills")
        return list(result) if isinstance(result, list) else []

    def get_collection_skill(self, skill_id: str) -> dict:
        return dict(self._request("GET", f"/api/collection-skills/{skill_id}"))

    def wait_collection_skill_ready(
        self,
        skill_id: str,
        timeout_seconds: int = 3600,
        interval_seconds: int = 5,
    ) -> dict:
        deadline = time.monotonic() + timeout_seconds
        while True:
            run = self.get_collection_skill(skill_id)
            status = run.get("status")
            if status == "ready":
                return run
            if status == "error":
                failed_reason = None
                scripts = run.get("scripts")
                if isinstance(scripts, dict):
                    failed_reason = scripts.get("failed_reason") or scripts.get("error")
                raise Book2SkillsClientError(
                    "Collection skill generation failed",
                    body=failed_reason or str(run),
                )
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for collection skill {skill_id} to be ready")
            if interval_seconds > 0:
                time.sleep(interval_seconds)

    def pack_collection_skill(self, skill_id: str) -> dict:
        return dict(self._request("POST", f"/api/collection-skills/{skill_id}/pack"))

    def retry_collection_skill(
        self,
        skill_id: str,
        *,
        user_goal: str | None = None,
        detect_conflicts: bool = True,
    ) -> dict:
        payload = {
            "user_goal": user_goal,
            "detect_conflicts": detect_conflicts,
        }
        return dict(self._request("POST", f"/api/collection-skills/{skill_id}/retry", json=payload))

    def download_collection_skill(self, skill_id: str, output_path: Path) -> dict:
        response = self._client.request("GET", f"/api/collection-skills/{skill_id}/download")
        if response.status_code >= 400:
            raise Book2SkillsClientError(
                "Book2Skills API request failed",
                status_code=response.status_code,
                endpoint=f"/api/collection-skills/{skill_id}/download",
                body=response.text,
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        return {"path": str(output_path), "bytes": len(response.content)}

