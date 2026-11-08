import asyncio

from fastembed import TextEmbedding

from .config import get_settings

# bge-small is trained to retrieve passages for queries that carry this prefix.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_model: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    global _model
    if _model is None:
        _model = TextEmbedding(model_name=get_settings().embed_model, threads=1)
    return _model


def embed_sync(texts: list[str]) -> list[list[float]]:
    return [vec.tolist() for vec in _get_model().embed(texts)]


async def embed_documents(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        out.extend(await asyncio.to_thread(embed_sync, texts[i : i + batch_size]))
    return out


async def embed_query(text: str) -> list[float]:
    result = await asyncio.to_thread(embed_sync, [QUERY_PREFIX + text])
    return result[0]


def to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
