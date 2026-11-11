from openai import AsyncOpenAI

from .config import get_settings


class LLMNotConfigured(RuntimeError):
    pass


_client: AsyncOpenAI | None = None


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.effective_llm_key:
            raise LLMNotConfigured("XAI_API_KEY (or LLM_API_KEY) is not set")
        _client = AsyncOpenAI(api_key=settings.effective_llm_key, base_url=settings.llm_base_url)
    return _client


async def complete(
    messages: list[dict],
    tools: list[dict] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 600,
):
    kwargs: dict = {
        "model": get_settings().chat_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
    response = await client().chat.completions.create(**kwargs)
    return response.choices[0].message


async def stream_complete(
    messages: list[dict],
    tools: list[dict] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 600,
):
    """Yield response deltas as they arrive (content tokens and/or tool-call fragments)."""
    kwargs: dict = {
        "model": get_settings().chat_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools
    stream = await client().chat.completions.create(**kwargs)
    async for chunk in stream:
        if chunk.choices:
            yield chunk.choices[0].delta
