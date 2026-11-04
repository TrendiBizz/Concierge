"""Claude (Anthropic API) client for web chat, SMS and demo-question generation.

Voice is separate: it uses the xAI Grok Voice API (see voice.py).
"""

import anthropic

from .config import get_settings


class LLMNotConfigured(RuntimeError):
    pass


_client: anthropic.AsyncAnthropic | None = None


def client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        key = get_settings().anthropic_api_key
        if not key:
            raise LLMNotConfigured("ANTHROPIC_API_KEY is not set")
        _client = anthropic.AsyncAnthropic(api_key=key)
    return _client


async def create(
    system: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: dict | None = None,
    max_tokens: int | None = None,
) -> anthropic.types.Message:
    """One Messages API call.

    Sampling parameters (temperature, top_p, top_k) are deliberately not sent: current Claude
    models reject non-default values. Reasoning depth is controlled with `effort` instead.
    """
    settings = get_settings()
    kwargs: dict = {
        "model": settings.chat_model,
        "max_tokens": max_tokens or settings.chat_max_tokens,
        "system": system,
        "messages": messages,
    }
    if settings.chat_effort:
        kwargs["output_config"] = {"effort": settings.chat_effort}
    if tools:
        kwargs["tools"] = tools
    if tool_choice:
        kwargs["tool_choice"] = tool_choice
    return await client().messages.create(**kwargs)


def text_of(response: anthropic.types.Message) -> str:
    """The visible text of a response (thinking and tool_use blocks are skipped)."""
    return "".join(block.text for block in response.content if block.type == "text").strip()
