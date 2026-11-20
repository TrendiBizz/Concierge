"""Rust telephone shell against the REAL Python internal API and a REAL PostgreSQL database.

Same scenario and same assertions as asterisk_db_integration.py (which drives the Python bridge), but the
AudioSocket side is the compiled `asterisk_shell` binary and every database/permission/CRM decision is made by the
real FastAPI app over /internal/voice/*. Only Grok (a local fake websocket) and the caller (a local AudioSocket
client) are simulated. No send worker, no real messages, no real calls.

Needs: an empty disposable PostgreSQL database (DATABASE_URL must contain 'fixture-only'), and the release binary
(`cargo build --release --bin asterisk_shell` in concierge-stack/core-rs, or set RUST_SHELL_BIN).
"""
import asyncio
import json
import os
import pathlib
import socket
import uuid

os.environ.setdefault("INTERNAL_TOKEN", "fixture-internal-token-0123456789abcdef")
os.environ.setdefault("PHONE_RECEPTIONIST_ENABLED", "true")
os.environ.setdefault("XAI_API_KEY", "fixture-only")
os.environ.setdefault("OUTBOX_ENABLED", "false")

import uvicorn
import websockets
from app import asterisk_bridge as b, db
from app.config import get_settings
from app.main import app

ROOT = pathlib.Path(__file__).resolve().parents[2]
BINARY = pathlib.Path(os.environ.get("RUST_SHELL_BIN", ROOT / "concierge-stack/core-rs/target/release/asterisk_shell"))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def wait_for(predicate, what, seconds=10):
    async with asyncio.timeout(seconds):
        while not await predicate():
            await asyncio.sleep(0.05)
    print("ok:", what)


async def main():
    cfg = get_settings()
    assert "fixture-only" in cfg.database_url, "Disposable fixture database required"
    assert BINARY.exists(), f"build the shell first: {BINARY}"
    assert cfg.internal_token, "INTERNAL_TOKEN must be set"

    # 1. The real API, served over a real socket.
    api_port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=api_port, log_level="warning", lifespan="on"))
    api_task = asyncio.create_task(server.serve())
    async with asyncio.timeout(30):
        while not server.started:
            await asyncio.sleep(0.05)
    pool = db.pool()
    assert not await pool.fetchval("SELECT count(*) FROM tenants"), "Empty fixture DB required"

    # 2. A fake Grok, identical in behaviour to the Python test's.
    transcripts = {}

    async def fake_grok(ws):
        update = json.loads(await ws.recv())
        instructions = update["session"]["instructions"]
        business = next(n for n in ("Alpha Workshop", "Beta Florist") if n in instructions)
        assert update["session"]["audio"]["input"]["format"]["rate"] == 8000
        await ws.send(json.dumps({"type": "session.updated"}))
        emitted = False
        async for raw in ws:
            event = json.loads(raw)
            if event["type"] == "input_audio_buffer.append" and not emitted:
                emitted = True
                await ws.send(json.dumps({
                    "type": "conversation.item.input_audio_transcription.completed",
                    "item_id": "same-call-local-id", "transcript": f"Message specifically for {business}"}))
                transcripts[business] = True

    grok = await websockets.serve(fake_grok, "127.0.0.1", 0)
    grok_port = grok.sockets[0].getsockname()[1]

    # 3. Two businesses, each with a private route, seeded exactly as the Python test seeds them.
    routes = []
    for i, (slug, name) in enumerate((("alpha", "Alpha Workshop"), ("beta", "Beta Florist"))):
        tenant = dict(await pool.fetchrow(
            "INSERT INTO tenants(slug,name,public_key,phone_enabled) VALUES($1,$2,$3,true) RETURNING *",
            slug, name, "fixture-" + slug))
        number = f"+649555010{i}"
        await pool.execute("INSERT INTO phone_numbers(e164,tenant_id,enabled) VALUES($1,$2,true)", number, tenant["id"])
        await pool.execute(
            "INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id) VALUES($1,'telephone',true,$2)",
            tenant["id"], uuid.uuid4())
        await pool.execute(
            "INSERT INTO managed_phone_setups(tenant_id,designated_number,connection,answer_mode,owner_number) "
            "VALUES($1,$2,'mobile_forwarding','unanswered',$3)", tenant["id"], number, f"+6421555010{i}")
        routes.append({"tenant": slug, "number": number, "port": free_port()})

    # 4. The Rust shell, pointed at the real API and the fake Grok.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "ASTERISK_ROUTES": json.dumps(routes),
        "ASTERISK_BIND": "127.0.0.1",
        "ASTERISK_PEERS": "127.0.0.1/32",
        "CONCIERGE_INTERNAL_URL": f"http://127.0.0.1:{api_port}",
        "CONCIERGE_INTERNAL_TOKEN": cfg.internal_token,
        "XAI_API_KEY": "fixture-only",
        "XAI_REALTIME_URL": f"ws://127.0.0.1:{grok_port}",
    }
    shell = await asyncio.create_subprocess_exec(str(BINARY), env=env, stdout=asyncio.subprocess.PIPE,
                                                 stderr=asyncio.subprocess.STDOUT)
    writers = []
    try:
        for route in routes:  # wait for each listener
            async with asyncio.timeout(10):
                while True:
                    try:
                        r, w = await asyncio.open_connection("127.0.0.1", route["port"])
                        break
                    except OSError:
                        await asyncio.sleep(0.1)
            writers.append((r, w))
            await b.send_packet(w, 1, uuid.uuid4().bytes)   # call UUID
            await b.send_packet(w, 0x10, b"\0" * 320)       # one frame of caller audio

        async def both_transcribed():
            return len(transcripts) == 2
        await wait_for(both_transcribed, "both businesses reached Grok with their own instructions")

        for _, w in writers:
            await b.send_packet(w, 0)                        # hangup

        async def calls_finished():
            return not await pool.fetchval("SELECT count(*) FROM phone_calls WHERE ended_at IS NULL")
        await wait_for(calls_finished, "both calls finished in the database")

        async def sms_queued():
            return await pool.fetchval("SELECT count(*) FROM outbox WHERE channel='sms'") == 2
        await wait_for(sms_queued, "owner SMS queued once per business")

        rows = await pool.fetch(
            "SELECT t.slug,l.message,o.to_addr,o.body FROM tenants t JOIN leads l ON l.tenant_id=t.id "
            "JOIN outbox o ON o.tenant_id=t.id WHERE o.channel='sms' ORDER BY t.slug")
        assert len(rows) == 2, [dict(r) for r in rows]
        for i, row in enumerate(rows):
            name, other = (("Alpha Workshop", "Beta Florist"), ("Beta Florist", "Alpha Workshop"))[i]
            assert name in row["message"] and other not in row["message"], dict(row)
            assert name in row["body"] and other not in row["body"], dict(row)
            assert row["to_addr"] == f"+6421555010{i}", dict(row)
        sent = await pool.fetchval("SELECT count(*) FROM outbox WHERE status='sent'")
        assert sent == 0, "no real sends"
        first = await pool.fetchrow("SELECT * FROM phone_calls ORDER BY started_at LIMIT 1")
        try:  # a call UUID cannot be replayed into another business
            await b.register(b.Route("beta", "+6495550101", 9102), first["call_sid"])
            raise AssertionError("Cross-business UUID replay accepted")
        except Exception as error:
            assert type(error).__name__ == "UniqueViolationError", type(error).__name__
        print("PASS: Rust shell + real API + real DB: two businesses -> Grok protocol -> separate CRM transcripts "
              "-> correct owner SMS queues; cross-business replay rejected; real sends=0")
    finally:
        for _, w in writers:
            w.close()
        shell.terminate()
        try:
            out, _ = await asyncio.wait_for(shell.communicate(), 5)
            if os.environ.get("SHELL_LOG"):
                print(out.decode(errors="replace")[-2000:])
        except asyncio.TimeoutError:
            shell.kill()
        grok.close()
        await grok.wait_closed()
        server.should_exit = True
        await api_task


asyncio.run(main())
