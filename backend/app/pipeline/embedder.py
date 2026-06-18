"""
向量嵌入模块 — 将 TextChunk 列表嵌入并存入 Qdrant
每本书使用独立的 Qdrant collection（book_id 为 collection 名）
"""
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.core.config import settings
from app.core.llm import close_embedding_client, get_embedding_client
from app.pipeline.chunker import TextChunk


class EmbeddingService:
    """管理向量嵌入和 Qdrant 存储"""

    def __init__(self):
        self.VECTOR_SIZE = settings.EMBEDDING_DIMENSION
        self.embeddings = get_embedding_client()
        self.qdrant = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
        )

    async def aclose(self) -> None:
        await close_embedding_client(self.embeddings)

    def ensure_collection(self, book_id: str) -> None:
        """确保 Qdrant collection 存在"""
        existing = [c.name for c in self.qdrant.get_collections().collections]
        if book_id not in existing:
            self.qdrant.create_collection(
                collection_name=book_id,
                vectors_config=VectorParams(size=self.VECTOR_SIZE, distance=Distance.COSINE),
            )

    async def embed_chunks(self, chunks: list[TextChunk], book_id: str) -> None:
        """批量嵌入并存入 Qdrant，分批处理避免 API 超限"""
        self.ensure_collection(book_id)

        batch_size = 50
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.text for c in batch]
            vectors = await self.embeddings.aembed_documents(texts)

            points = [
                PointStruct(
                    id=chunk.chunk_index,
                    vector=vector,
                    payload={
                        "book_id": chunk.book_id,
                        "chapter_num": chunk.chapter_num,
                        "chapter_title": chunk.chapter_title,
                        "text": chunk.text,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                    },
                )
                for chunk, vector in zip(batch, vectors)
            ]
            self.qdrant.upsert(collection_name=book_id, points=points)

    def delete_book(self, book_id: str) -> None:
        """删除书籍对应的 collection（用于清理）"""
        existing = [c.name for c in self.qdrant.get_collections().collections]
        if book_id in existing:
            self.qdrant.delete_collection(book_id)
