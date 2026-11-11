import asyncio
from types import SimpleNamespace

from app import rag


def test_retrieve_caches_repeat_query(monkeypatch):
    calls = {"embed": 0}

    async def fake_embed(text):
        calls["embed"] += 1
        return [0.01] * 384

    class Pool:
        async def fetch(self, *args, **kwargs):
            return []

    monkeypatch.setattr(rag, "embed_query", fake_embed)
    monkeypatch.setattr(rag, "db", SimpleNamespace(pool=lambda: Pool()))

    async def scenario():
        await rag.retrieve("cache-test-tenant", "pricing question")
        await rag.retrieve("cache-test-tenant", "pricing question")

    asyncio.run(scenario())
    assert calls["embed"] == 1
