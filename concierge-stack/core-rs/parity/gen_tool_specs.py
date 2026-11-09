"""Dump the tool specs from the live Python so the Rust copy cannot drift by retyping.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_tool_specs.py > ../concierge-stack/core-rs/src/tool_specs.json
"""
import json
import os
import sys

os.environ.setdefault("OUTBOX_ENABLED", "false")
sys.path.insert(0, os.getcwd())
from app import tools  # noqa: E402

out = [{k: v for k, v in s.items() if k != "available"} for s in tools.TOOL_SPECS]
print(json.dumps(out, indent=1, ensure_ascii=False))
