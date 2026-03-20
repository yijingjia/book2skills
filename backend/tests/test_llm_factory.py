from unittest.mock import patch

from app.core.config import settings
from app.core.llm import get_chat_model, get_embedding_client, get_generation_model, get_llm_client


def test_llm_factory_openai():
    with patch.object(settings, "LLM_PROVIDER", "openai"):
        # AsyncOpenAI client doesn't easily expose base_url in a simple way to check without deeper inspection
        # but we can check the model helpers
        assert get_generation_model() == settings.OPENAI_GENERATION_MODEL
        assert get_chat_model() == settings.OPENAI_CHAT_MODEL

def test_llm_factory_qwen():
    with patch.object(settings, "LLM_PROVIDER", "qwen"):
        with patch.object(settings, "QWEN_API_KEY", "test-key"):
            client = get_llm_client()
            assert client.api_key == "test-key"
            assert str(client.base_url).rstrip("/") == settings.QWEN_BASE_URL.rstrip("/")
            assert get_generation_model() == settings.QWEN_GENERATION_MODEL
            assert get_chat_model() == settings.QWEN_CHAT_MODEL

def test_embedding_factory_openai():
    with patch.object(settings, "EMBEDDING_PROVIDER", "openai"):
        client = get_embedding_client()
        assert client.model == settings.OPENAI_EMBEDDING_MODEL

def test_embedding_factory_qwen():
    with patch.object(settings, "EMBEDDING_PROVIDER", "qwen"):
        with patch.object(settings, "QWEN_API_KEY", "test-key"):
            client = get_embedding_client()
            assert client.model == settings.QWEN_EMBEDDING_MODEL
            assert client.openai_api_key.get_secret_value() == "test-key"
            assert client.openai_api_base == settings.QWEN_BASE_URL
