"""Scripted conversation check using a Grok TEXT model (not the voice model).

Drives the real Concierge agent and the real hang-up guard with typed caller lines, and prints
what it says, which tools it calls, and whether the call was hung up. Needs XAI_API_KEY (loaded
from .env by run-chat-check.sh). Uses a temp data dir, so nothing touches your real bookings.
A few cents of API usage per run. It cannot judge how the voice sounds.
"""
import asyncio
import os
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "agent"))
_tmp = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = _tmp.name
os.environ["MESSAGES_FILE"] = str(Path(_tmp.name) / "messages.jsonl")
os.environ["FAREWELL_GRACE_SECONDS"] = "2"
os.environ.pop("HUMAN_TRANSFER_NUMBER", None)
# Safety: this check uses made-up callers, so it must never really text or email anyone,
# even though run-chat-check.sh loads the real .env. Everything goes to the temp outbox only.
for _var in ("SMS_PROVIDER", "TELNYX_API_KEY", "SMS_FROM", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM"):
    os.environ.pop(_var, None)

from livekit import rtc  # noqa: E402
from livekit.agents import AgentSession  # noqa: E402
from livekit.plugins import openai  # noqa: E402

import agent  # noqa: E402

MODEL = os.environ.get("CHECK_MODEL", "grok-4.20-0309-non-reasoning")

SCENARIOS = {
    "pen testing": ["Hello.", "I'm interested in penetration testing. How much does it cost?"],
    "concierge": ["Hello.", "I'd like to hear about Concierge please. What does it cost?"],
    "seo": ["Hello.", "Tell me about your SEO service and the price."],
    "unsure caller": ["Hi, I run a plumbing business and I'm not sure what you do."],
    "booking and goodbye": [
        "Hello.",
        "I want to know about SEO.",
        "Sounds good. Can I book a consultation on Monday?",
        "Nine thirty please. My name is Sam Taylor.",
        "Yes, the number I'm calling from is fine.",
        "Yes, please text me a confirmation, but no email.",
        "No, nothing else. Goodbye.",
    ],
    "message with text confirmation": [
        "Hello.",
        "I'd like someone to call me about SEO. My name is Alex Rivera.",
        "The number I'm calling from is fine.",
        "Yes, please text me a confirmation.",
        "That's all, bye.",
    ],
    "message and goodbye": [
        "Hello.",
        "I'd like someone to call me about Concierge. My name is Alex Rivera.",
        "The number I'm calling from is fine.",
        "That's all, bye.",
    ],
}


class FakeJob:
    def __init__(self):
        sip = types.SimpleNamespace(
            kind=rtc.ParticipantKind.PARTICIPANT_KIND_SIP,
            identity="sip_1",
            attributes={"sip.phoneNumber": "+64211234567"},
        )
        self.room = types.SimpleNamespace(name="chat-check", remote_participants={"p": sip})
        self.ended = False

    async def delete_room(self):
        self.ended = True

    def shutdown(self, reason=""):
        self.ended = True


async def run_scenario(name, turns):
    print(f"\n=== {name} ===")
    job = FakeJob()
    async with AgentSession(llm=openai.LLM.with_x_ai(model=MODEL)) as session:
        await session.start(agent.Concierge(job))
        guard = agent.CallGuard(job, session)
        guard.start()
        for line in turns:
            print(f"CALLER: {line}")
            result = await session.run(user_input=line)
            for ev in result.events:
                item = getattr(ev, "item", ev)
                kind = getattr(item, "type", type(item).__name__)
                if kind == "message" and getattr(item, "role", "") == "assistant":
                    print(f"AGENT : {item.text_content}")
                elif kind == "function_call":
                    print(f"  [tool] {item.name}({item.arguments})")
                elif kind == "function_call_output":
                    print(f"  [result] {str(item.output)[:200]}")
        await asyncio.sleep(4)  # give the guard time to act after a farewell
        guard.stop()
    print(f"hung up: {job.ended}")


async def main():
    only = sys.argv[1:] or list(SCENARIOS)
    for name in only:
        await run_scenario(name, SCENARIOS[name])


if __name__ == "__main__":
    asyncio.run(main())
