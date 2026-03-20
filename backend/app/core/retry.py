"""
统一 LLM 重试策略 (tenacity)

使用方式：
    from app.core.retry import llm_retry

    @llm_retry
    async def my_llm_call():
        ...
"""
import logging

from tenacity import (
    after_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """判断异常是否应该重试：
    - 频率限制 (429 / RateLimitError)
    - 连接超时 / 临时网络错误

    不重试：
    - LLM 输出格式错误（ValidationError / ValueError）
      → 同一 prompt 重试通常得到同质量结果，白白消耗 token，应直接跳过该 chunk
    - 参数错误、认证失败等永久性错误
    """
    msg = str(exc).lower()
    return (
        "429" in msg
        or "rate_limit" in msg
        or "ratelimit" in msg
        or "too many requests" in msg
        or "connection" in msg
        or "timeout" in msg
        or "service_unavailable" in msg
        or "503" in msg
        or "502" in msg
    )


llm_retry = retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    after=after_log(logger, logging.WARNING),
    reraise=True,
)
