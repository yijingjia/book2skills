from langchain_openai import OpenAIEmbeddings
from openai import AsyncOpenAI

from app.core.config import settings


def get_llm_client() -> AsyncOpenAI:
    """获取配置好的 LLM 客户端"""
    if settings.LLM_PROVIDER == "qwen":
        return AsyncOpenAI(
            api_key=settings.QWEN_API_KEY,
            base_url=settings.QWEN_BASE_URL
        )
    if settings.LLM_PROVIDER == "glm":
        return AsyncOpenAI(
            api_key=settings.GLM_API_KEY,
            base_url=settings.GLM_BASE_URL
        )
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

def get_embedding_client() -> OpenAIEmbeddings:
    """获取配置好的 Embedding 客户端"""
    if settings.EMBEDDING_PROVIDER == "qwen":
        return OpenAIEmbeddings(
            model=settings.QWEN_EMBEDDING_MODEL,
            openai_api_key=settings.QWEN_API_KEY,
            openai_api_base=settings.QWEN_BASE_URL,
        )
    return OpenAIEmbeddings(
        model=settings.OPENAI_EMBEDDING_MODEL,
        api_key=settings.OPENAI_API_KEY,
    )

def get_generation_model() -> str:
    """获取当前 provider 的生成模型名称"""
    if settings.LLM_PROVIDER == "qwen":
        return settings.QWEN_GENERATION_MODEL
    if settings.LLM_PROVIDER == "glm":
        return settings.GLM_GENERATION_MODEL
    return settings.OPENAI_GENERATION_MODEL

def get_chat_model() -> str:
    """获取当前 provider 的聊天模型名称"""
    if settings.LLM_PROVIDER == "qwen":
        return settings.QWEN_CHAT_MODEL
    if settings.LLM_PROVIDER == "glm":
        return settings.GLM_CHAT_MODEL
    return settings.OPENAI_CHAT_MODEL
