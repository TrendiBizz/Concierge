"""N3: LLM retry, circuit breaker and secondary-provider failover."""
import asyncio
from types import SimpleNamespace

import httpx
import openai
import pytest

from app import llm
from app.config import get_settings


def _req():
    return httpx.Request("POST", "https://x.invalid/v1/chat/completions")


def _status_error(code):
    return openai.APIStatusError("boom", response=httpx.Response(code, request=_req()), body=None)


class FakeClient:
    """Plays a script of results/exceptions, one per create() call."""
    def __init__(self, script, name):
        self.script, self.name, self.calls = list(script), name, 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kw):
        self.calls += 1
        item = self.script.pop(0) if self.script else self.script_default()
        if isinstance(item, Exception):
            raise item
        return item

    def script_default(self):
        raise AssertionError("unexpected extra call to " + self.name)


def reply(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


class Stream:
    def __init__(self, parts, fail_after=None):
        self.parts, self.fail_after = parts, fail_after

    def __aiter__(self):
        async def gen():
            for i, p in enumerate(self.parts):
                if self.fail_after is not None and i == self.fail_after:
                    raise openai.APIConnectionError(request=_req())
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=p))])
        return gen()


@pytest.fixture
def env(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_fallback_base_url", "https://fb.invalid/v1")
    monkeypatch.setattr(s, "llm_fallback_api_key", "k")
    monkeypatch.setattr(s, "llm_fallback_model", "fb-model")
    monkeypatch.setattr(s, "llm_retry_attempts", 2)
    monkeypatch.setattr(s, "llm_breaker_threshold", 2)
    monkeypatch.setattr(s, "llm_breaker_cooldown_seconds", 60.0)
    sleeps = []

    async def fake_sleep(t):
        sleeps.append(t)
    monkeypatch.setattr(llm, "_sleep", fake_sleep)
    clock = {"t": 1000.0}
    monkeypatch.setattr(llm, "_now", lambda: clock["t"])
    llm.reset()
    holder = SimpleNamespace(sleeps=sleeps, clock=clock)

    def install(primary, fallback):
        monkeypatch.setattr(llm, "client", lambda: primary)
        monkeypatch.setattr(llm, "fallback_client", lambda: fallback)
    holder.install = install
    yield holder
    llm.reset()


def run(coro):
    return asyncio.run(coro)


def test_retry_then_success_without_fallback(env):
    p = FakeClient([_status_error(503), reply("ok")], "p")
    f = FakeClient([], "f")
    env.install(p, f)
    msg = run(llm.complete([{"role": "user", "content": "hi"}]))
    assert msg.content == "ok" and p.calls == 2 and f.calls == 0
    assert len(env.sleeps) == 1 and llm.status()["consecutive_failures"] == 0


def test_exhausted_retries_fail_over(env):
    p = FakeClient([openai.APITimeoutError(request=_req())] * 3, "p")
    f = FakeClient([reply("from fallback")], "f")
    env.install(p, f)
    assert run(llm.complete([])).content == "from fallback"
    assert p.calls == 3 and f.calls == 1 and llm.status()["fallback_calls"] == 1
    assert len(env.sleeps) == 2  # exponential backoff between the three tries
    assert env.sleeps[1] > env.sleeps[0]


def test_bad_request_never_fails_over(env):
    p = FakeClient([_status_error(400)], "p")
    f = FakeClient([reply("no")], "f")
    env.install(p, f)
    with pytest.raises(openai.APIStatusError):
        run(llm.complete([]))
    assert p.calls == 1 and f.calls == 0


def test_auth_error_fails_over_without_retry(env):
    p = FakeClient([_status_error(401)], "p")
    f = FakeClient([reply("fb")], "f")
    env.install(p, f)
    assert run(llm.complete([])).content == "fb"
    assert p.calls == 1 and not env.sleeps


def test_no_fallback_configured_raises_after_retries(env, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_fallback_api_key", "")
    p = FakeClient([_status_error(500)] * 3, "p")
    env.install(p, FakeClient([], "f"))
    with pytest.raises(openai.APIStatusError):
        run(llm.complete([]))
    assert p.calls == 3 and not llm.status()["breaker_open"]


def test_breaker_opens_skips_primary_then_probes(env):
    p = FakeClient([_status_error(500)] * 6 + [reply("primary back")], "p")
    f = FakeClient([reply("f1"), reply("f2"), reply("f3")], "f")
    env.install(p, f)
    run(llm.complete([])); run(llm.complete([]))      # 2 failed requests -> breaker opens
    assert llm.status()["breaker_open"] and p.calls == 6
    assert run(llm.complete([])).content == "f3" and p.calls == 6  # primary skipped while open
    env.clock["t"] += 61                               # cooldown over: one probe
    assert run(llm.complete([])).content == "primary back"
    assert not llm.status()["breaker_open"] and llm.status()["consecutive_failures"] == 0


def test_stream_fails_over_before_first_chunk(env):
    class Dead:
        chat = SimpleNamespace(completions=SimpleNamespace(create=None))
    p = FakeClient([_status_error(502)] * 3, "p")
    f = FakeClient([Stream(["a", "b"])], "f")

    async def create_fb(**kw):
        f.calls += 1
        return Stream(["a", "b"])
    f.chat.completions.create = create_fb
    env.install(p, f)

    async def collect():
        return [d.content async for d in llm.stream_complete([])]
    assert run(collect()) == ["a", "b"] and f.calls == 1


def test_stream_midway_failure_is_not_spliced(env):
    p = FakeClient([Stream(["a", "b", "c"], fail_after=1)], "p")
    f = FakeClient([], "f")
    env.install(p, f)

    async def collect():
        out = []
        async for d in llm.stream_complete([]):
            out.append(d.content)
        return out
    with pytest.raises(openai.APIConnectionError):
        run(collect())
    assert f.calls == 0
