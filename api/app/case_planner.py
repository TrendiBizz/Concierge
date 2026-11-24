"""One planner call for a new case. The model proposes. Concierge decides.

The call is a single `claude -p` in plan mode. Plan mode cannot edit files, and this is not a
chat loop. The reply must be one JSON plan. `case_policy` accepts or rejects it whole.
A rejected plan is discarded. An accepted plan is written as a to-do for the owner. Nothing
here sends email, SMS, or a quote.

Turn it on with CASE_PLANNER=claude on a machine where the `claude` command is the Max-plan
login. The API container does not have that command, so the call no-ops there instead of
using the configured LLM key.
"""
from __future__ import annotations

import json
import shutil
import subprocess

from . import case_policy
from .config import get_settings

OPERATIONS = ", ".join(sorted(case_policy.OPERATIONS))


def prompt_for(lead: dict) -> str:
    """Facts the model may see. Identifiers the model must not set are left out."""
    message = (lead.get("message") or "")[:1000]
    channel = (lead.get("channel") or "")[:40]
    return (
        "Reply with one JSON object and no other text. "
        "Shape: {\"confidence\": 0.0 to 1.0, \"actions\": [{\"op\": \"...\", \"params\": {}}]}. "
        f"op must be one of: {OPERATIONS}. "
        "Do not include tenant, case, lead, token, or secret fields. "
        "Do not ask to send anything. "
        f"Channel: {channel}\n"
        f"Customer message:\n{message}"
    )


def parse_plan(reply: str) -> dict | None:
    start = reply.find("{")
    end = reply.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        plan = json.loads(reply[start:end + 1])
    except json.JSONDecodeError:
        return None
    return plan if isinstance(plan, dict) else None


def decide(reply: str) -> dict | None:
    """Return an owner to-do for a valid plan, or None when the plan is refused.

    Shadow mode is the default: customer-facing and mutating operations are not carried out.
    The to-do records what was proposed and why it was not executed.
    """
    plan = parse_plan(reply or "")
    verdict = case_policy.validate_plan(plan)
    if not verdict["ok"]:
        return None
    lines = []
    for action in verdict["plan"]["actions"]:
        decision = case_policy.permit({"autonomy": "shadow"}, action["op"])
        lines.append(f"{action['op']}: {decision['reason']}")
    return {"title": "Planner suggestion", "notes": "\n".join(lines)[:2000]}


def claude_plan(prompt: str, timeout: float = 60.0) -> str:
    """One headless Claude Code call. Plan mode so the process cannot edit the repo."""
    completed = subprocess.run(
        ["claude", "-p", "--permission-mode", "plan", prompt],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return completed.stdout or ""


def note_for(lead: dict, run=claude_plan) -> dict | None:
    """The to-do for this case, or None when planning is off or the plan is refused."""
    if get_settings().case_planner != "claude":
        return None
    if run is claude_plan and shutil.which("claude") is None:
        return None
    try:
        reply = run(prompt_for(lead))
    except (OSError, subprocess.TimeoutExpired):
        return None
    return decide(reply)
