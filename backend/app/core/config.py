from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Provider Selection
    LLM_PROVIDER: str = "qwen"  # openai, qwen, glm
    EMBEDDING_PROVIDER: str = "openai"  # openai, qwen

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_GENERATION_MODEL: str = "gpt-5.2"
    OPENAI_CHAT_MODEL: str = "gpt-5-mini"

    # Qwen (DashScope)
    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_GENERATION_MODEL: str = "qwen3-max"
    QWEN_CHAT_MODEL: str = "qwen-plus"
    QWEN_EMBEDDING_MODEL: str = "text-embedding-v4"

    # GLM (Zhipu AI)
    GLM_API_KEY: str = ""
    GLM_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4/"
    GLM_GENERATION_MODEL: str = "glm-5"
    GLM_CHAT_MODEL: str = "glm-4.7"

    # Embedding Dimension
    EMBEDDING_DIMENSION: int = 1536  # Default for text-embedding-3-small and text-embedding-v3

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Qdrant
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""

    # Storage
    STORAGE_TYPE: str = "local"
    STORAGE_LOCAL_PATH: str = "./storage"

    # App
    DEBUG: bool = False
    MAX_FILE_SIZE_MB: int = 50
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 150
    RETRIEVAL_TOP_K: int = 5  # Final results returned to the caller
    RETRIEVAL_CANDIDATE_K: int = 50  # Wide candidate pool for hybrid search before reranking
    RETRIEVAL_MIN_SCORE: float = 0.0
    SKILL_RETRIEVAL_TOP_K: int = 8  # Final skill modules returned for playground/refinement
    # Hybrid search tuning
    RETRIEVAL_VECTOR_WEIGHT: float = 0.6  # Vector similarity weight in BM25 hybrid scoring
    RETRIEVAL_BM25_WEIGHT: float = 0.4  # BM25 keyword weight in BM25 hybrid scoring
    # Query expansion (off by default to save LLM cost; enable for better recall on short queries)
    RETRIEVAL_USE_QUERY_EXPANSION: bool = False
    RETRIEVAL_QUERY_EXPANSION_N: int = 3  # Number of alternative queries to generate
    COLLECTION_NORMALIZATION_TOP_K: int = 8
    COLLECTION_NORMALIZATION_MIN_SIMILARITY: float = 0.35  # Garbage floor only; top-k drives recall because Chinese KU cosine values are compressed.
    COLLECTION_SAME_AS_JUDGE_BATCH_SIZE: int = 30
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]


settings = Settings()
