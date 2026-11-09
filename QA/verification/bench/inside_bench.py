"""Runs INSIDE the benchmark container: times the retrieval stages and the phone-call audio conversion."""
import asyncio
import base64
import os
import time

import asyncpg


def stats(label, ms):
    ms = sorted(ms)
    print(f"{label:<54} p50={ms[len(ms) // 2]:7.2f}ms  p95={ms[int(len(ms) * .95) - 1]:7.2f}ms")


async def retrieval():
    from app import db, embeddings, rag
    db._pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=2)
    tid = await db._pool.fetchval("select id from tenants where slug='bench'")
    await embeddings.embed_query("warm up")
    for label, fn in [
        ("embed the visitor's question (CPU, ONNX)", lambda: embeddings.embed_query("What do you charge for a hot water cylinder?")),
        ("retrieve = embed + pgvector search", lambda: rag.retrieve(tid, "What do you charge for a hot water cylinder?")),
        ("one small DB query", lambda: db._pool.fetchval("select 1")),
    ]:
        ms = []
        for _ in range(60):
            t = time.perf_counter(); await fn(); ms.append((time.perf_counter() - t) * 1000)
        stats(label, ms)


# ---- phone audio: G.711 mu-law <-> PCM16, and 8 kHz <-> 24 kHz
def build_tables():
    dec = []
    for b in range(256):
        u = ~b & 0xFF
        sign, exp, mant = u & 0x80, (u >> 4) & 7, u & 0x0F
        s = (((mant << 3) + 0x84) << exp) - 0x84
        dec.append(-s if sign else s)
    return dec


DEC = build_tables()


def ulaw_encode(s):
    sign = 0x80 if s < 0 else 0
    s = min(abs(s), 32635) + 0x84
    exp = min(max(s.bit_length() - 8, 0), 7)
    return ~(sign | (exp << 4) | ((s >> (exp + 3)) & 0x0F)) & 0xFF


def py_in(ulaw: bytes) -> bytes:           # phone -> model: mu-law 8k -> pcm16 24k (x3 linear) -> base64
    pcm = [DEC[b] for b in ulaw]
    out = []
    for i, a in enumerate(pcm):
        b = pcm[i + 1] if i + 1 < len(pcm) else a
        out += (a, a + (b - a) // 3, a + 2 * (b - a) // 3)
    return base64.b64encode(b"".join(int(x).to_bytes(2, "little", signed=True) for x in out))


def py_out(pcm24: bytes) -> bytes:         # model -> phone: pcm16 24k -> 8k (average of 3) -> mu-law -> base64
    n = len(pcm24) // 2
    samples = [int.from_bytes(pcm24[i * 2:i * 2 + 2], "little", signed=True) for i in range(n)]
    return base64.b64encode(bytes(ulaw_encode(sum(samples[i:i + 3]) // 3) for i in range(0, n - 2, 3)))


def audio():
    import numpy as np
    seconds = 10
    ulaw = bytes((i * 37) % 256 for i in range(8000 * seconds))
    pcm24 = (np.sin(np.arange(24000 * seconds) / 20.0) * 12000).astype("<i2").tobytes()

    def np_in(u: bytes) -> bytes:
        pcm = np.array(DEC, dtype=np.int32)[np.frombuffer(u, dtype=np.uint8)]
        x = np.arange(len(pcm) * 3) / 3.0
        return base64.b64encode(np.interp(x, np.arange(len(pcm)), pcm).astype("<i2").tobytes())

    def np_out(p: bytes) -> bytes:
        s = np.frombuffer(p, dtype="<i2").astype(np.int32)
        s = s[: len(s) // 3 * 3].reshape(-1, 3).mean(axis=1).astype(np.int32)
        sign = (s < 0) * 0x80
        m = np.minimum(np.abs(s), 32635) + 0x84
        exp = np.clip(np.floor(np.log2(m)).astype(np.int32) - 7, 0, 7)
        u = (~(sign | (exp << 4) | ((m >> (exp + 3)) & 0x0F))) & 0xFF
        return base64.b64encode(u.astype(np.uint8).tobytes())

    print(f"\nAudio conversion for {seconds} seconds of call audio, each direction:")
    for name, fi, fo in [("pure Python", py_in, py_out), ("numpy", np_in, np_out)]:
        reps = 3 if name == "pure Python" else 30
        t = time.perf_counter()
        for _ in range(reps):
            fi(ulaw)
        tin = (time.perf_counter() - t) / reps * 1000 / seconds
        t = time.perf_counter()
        for _ in range(reps):
            fo(pcm24)
        tout = (time.perf_counter() - t) / reps * 1000 / seconds
        per_call = (tin + tout) / 1000           # CPU-seconds spent per second of a two-way call
        print(f"  {name:<12} caller->model {tin:8.3f} ms/s   model->caller {tout:8.3f} ms/s   "
              f"=> one core at 50% load carries ~{int(0.5 / per_call):>6} simultaneous calls")


asyncio.run(retrieval())
audio()
