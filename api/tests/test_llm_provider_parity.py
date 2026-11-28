"""Text chat and email use one LLM seam (app/llm.py), so Gemini and OpenAI behave the same to callers."""
import re
from pathlib import Path

from app import llm

APP = Path(__file__).resolve().parents[1] / "app"
MSGS = [{"role": "user", "content": "hi"}]
TOOLS = [{"type": "function", "function": {"name": "capture_lead", "parameters": {"type": "object"}}}]


def test_gemini_and_classic_openai_models_get_same_request_shape():
    for model in ("gemini-3.8-flash", "gpt-4.1-mini"):
        kw = llm._kwargs(model, MSGS, TOOLS, 0.3, 500)
        assert kw == {"model": model, "messages": MSGS, "temperature": 0.3, "max_tokens": 500, "tools": TOOLS}


def test_openai_reasoning_models_use_max_completion_tokens_and_no_temperature():
    for model in ("gpt-5-mini", "gpt-5.4", "o3"):
        kw = llm._kwargs(model, MSGS, TOOLS, 0.3, 500, stream=True)
        assert kw["max_completion_tokens"] == 500 and kw["stream"] is True and kw["tools"] == TOOLS
        assert "max_tokens" not in kw and "temperature" not in kw


def test_every_text_and_email_path_goes_through_llm_module():
    direct = [p.name for p in APP.glob("*.py")
              if p.name != "llm.py" and re.search(r"AsyncOpenAI|chat\.completions", p.read_text(encoding="utf-8"))]
    assert direct == []
    for name in ("chat.py", "email_drafts.py", "ingest.py", "owner_ask.py", "quotations.py", "call_insights.py"):
        assert "llm.complete" in (APP / name).read_text(encoding="utf-8") or "llm.stream_complete" in (APP / name).read_text(encoding="utf-8")
    # The email secretary answers through chat.py, i.e. the same prompts, tools, RAG and CRM capture.
    assert "chat" in (APP / "email_secretary.py").read_text(encoding="utf-8")
