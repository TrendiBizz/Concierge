"""Chat/email/insight LLM access with retry, circuit breaker and secondary-provider failover (N3).

One vendor outage used to mean every web chat returned a 502. Now:
  * transient errors (timeouts, connection errors, 429, 5xx) are retried on the primary with
    exponential backoff;
  * auth failures (401/403) skip the retries, since they will not fix themselves, but still fail over;
  * after `llm_breaker_threshold` consecutive failed requests the breaker opens and requests go
    straight to the secondary for `llm_breaker_cooldown_seconds`, then one probe tries the primary;
  * the secondary is any OpenAI-compatible provider with tool-call support, configured by
    LLM_FALLBACK_BASE_URL / LLM_FALLBACK_API_KEY / LLM_FALLBACK_MODEL. Not configured = no failover
    (retries still apply). Bad requests (400/422) are our bug and never fail over.
A stream only fails over before its first chunk: half an answer cannot be spliced safely.
"""

import asyncio
import logging
import random
import time

import openai
from openai import AsyncOpenAI

from .config import get_settings

log = logging.getLogger("concierge.llm")


class LLMNotConfigured(RuntimeError):
    pass


_client: AsyncOpenAI | None = None
_fallback_client: AsyncOpenAI | None = None

# Breaker state for the primary provider (process-local; each worker learns independently).
_state = {"failures": 0, "open_until": 0.0, "fallback_calls": 0, "primary_errors": 0}

_sleep = asyncio.sleep  # replaced in tests
_now = time.monotonic   # replaced in tests


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.effective_llm_key:
            raise LLMNotConfigured("LLM_API_KEY (or GEMINI_API_KEY) is not set")
        # We own retries (so the breaker sees them): the SDK default of silent retries is off.
        _client = AsyncOpenAI(api_key=settings.effective_llm_key, base_url=settings.llm_base_url,
                              timeout=settings.llm_timeout_seconds, max_retries=0)
    return _client


def fallback_configured() -> bool:
    s = get_settings()
    return bool(s.llm_fallback_api_key and s.llm_fallback_base_url and s.llm_fallback_model)


def fallback_client() -> AsyncOpenAI:
    global _fallback_client
    if _fallback_client is None:
        s = get_settings()
        _fallback_client = AsyncOpenAI(api_key=s.llm_fallback_api_key, base_url=s.llm_fallback_base_url,
                                       timeout=s.llm_timeout_seconds, max_retries=0)
    return _fallback_client


def status() -> dict:
    """Operational snapshot (no secrets) for health checks and tests."""
    return {"breaker_open": _state["open_until"] > _now(), "consecutive_failures": _state["failures"],
            "primary_errors": _state["primary_errors"], "fallback_calls": _state["fallback_calls"],
            "fallback_configured": fallback_configured()}


def reset() -> None:
    global _client, _fallback_client
    _client = _fallback_client = None
    _state.update(failures=0, open_until=0.0, fallback_calls=0, primary_errors=0)


def _http_status(error: Exception) -> int | None:
    return getattr(error, "status_code", None)


def _transient(error: Exception) -> bool:
    if isinstance(error, (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError)):
        return True
    code = _http_status(error)
    return isinstance(error, openai.APIStatusError) and code is not None and (code >= 500 or code in (408, 409, 429))


def _fail_over_worthy(error: Exception) -> bool:
    return _transient(error) or _http_status(error) in (401, 403)


def _record_failure() -> None:
    s = get_settings()
    _state["failures"] += 1
    _state["primary_errors"] += 1
    if _state["failures"] >= s.llm_breaker_threshold and fallback_configured():
        _state["open_until"] = _now() + s.llm_breaker_cooldown_seconds
        log.warning("LLM primary breaker open for %ss after %s consecutive failures",
                    s.llm_breaker_cooldown_seconds, _state["failures"])


def _record_success() -> None:
    _state["failures"] = 0
    _state["open_until"] = 0.0


def _kwargs(model: str, messages, tools, temperature, max_tokens, stream=False) -> dict:
    kwargs: dict = {"model": model, "messages": messages, "temperature": temperature,
                    "max_tokens": max_tokens}
    if stream:
        kwargs["stream"] = True
    if tools:
        kwargs["tools"] = tools
    return kwargs


def _primary_allowed() -> bool:
    return not (fallback_configured() and _state["open_until"] > _now())


async def _backoff(attempt: int) -> None:
    await _sleep(min(4.0, 0.4 * (2 ** attempt)) * (0.75 + random.random() * 0.5))


async def _call(make_primary, make_fallback):
    """Run a request against the primary with retries, then the secondary."""
    attempts = 1 + max(0, get_settings().llm_retry_attempts)
    last: Exception | None = None
    if _primary_allowed():
        for attempt in range(attempts):
            try:
                result = await make_primary()
                _record_success()
                return result
            except Exception as error:  # noqa: BLE001 - classified below
                if not _fail_over_worthy(error):
                    raise
                last = error
                log.warning("LLM primary failed (%s, try %s/%s)", type(error).__name__, attempt + 1, attempts)
                if not _transient(error) or attempt == attempts - 1:
                    break
                await _backoff(attempt)
        _record_failure()
    if not fallback_configured():
        if last is not None:
            raise last
        raise LLMNotConfigured("LLM unavailable")
    _state["fallback_calls"] += 1
    log.warning("LLM request served by the secondary provider")
    return await make_fallback()


async def complete(
    messages: list[dict],
    tools: list[dict] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 600,
):
    s = get_settings()

    async def primary():
        r = await client().chat.completions.create(**_kwargs(s.chat_model, messages, tools, temperature, max_tokens))
        return r.choices[0].message

    async def secondary():
        r = await fallback_client().chat.completions.create(
            **_kwargs(s.llm_fallback_model, messages, tools, temperature, max_tokens))
        return r.choices[0].message

    return await _call(primary, secondary)


async def stream_complete(
    messages: list[dict],
    tools: list[dict] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 600,
):
    """Yield response deltas as they arrive (content tokens and/or tool-call fragments)."""
    s = get_settings()

    async def open_stream(get_client, model):
        stream = await get_client().chat.completions.create(
            **_kwargs(model, messages, tools, temperature, max_tokens, stream=True))
        iterator = stream.__aiter__()
        # Pull the first chunk inside the guarded call so a dead provider fails over cleanly.
        first = await iterator.__anext__()
        return first, iterator

    async def primary():
        return await open_stream(client, s.chat_model)

    async def secondary():
        return await open_stream(fallback_client, s.llm_fallback_model)

    try:
        first, iterator = await _call(primary, secondary)
    except StopAsyncIteration:
        return
    if first.choices:
        yield first.choices[0].delta
    async for chunk in iterator:
        if chunk.choices:
            yield chunk.choices[0].delta
