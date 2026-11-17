#!/usr/bin/env python3
"""Idempotently set the subscription-first fallback chain in a Hermes profile config.

Run inside the container: apply-fallback.py [profile]  (default trendi-master).
Order: Codex (ChatGPT plan) -> Grok (SuperGrok OAuth) -> DeepSeek API (last resort).
The primary (Claude via Max) is set in the profile's model: block and is not touched.
"""
import sys
from pathlib import Path

import yaml

CHAIN = [
    {"provider": "openai-codex", "model": "gpt-6.1-sol"},
    {"provider": "xai-oauth", "model": "grok-4.7"},
    {"provider": "deepseek", "model": "deepseek-v4-flash"},
]


def main() -> int:
    profile = sys.argv[1] if len(sys.argv) > 1 else "trendi-master"
    path = Path("/opt/data/profiles") / profile / "config.yaml"
    cfg = yaml.safe_load(path.read_text()) or {}
    if cfg.get("fallback_model") == CHAIN:
        print(f"{profile}: fallback chain already set")
        return 0
    cfg["fallback_model"] = CHAIN
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    print(f"{profile}: fallback chain written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
