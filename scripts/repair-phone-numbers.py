#!/usr/bin/env python3
"""Repair phone numbers written by the old normaliser.

SAFE BY DEFAULT: this only surveys unless you pass --apply. Run it once without --apply to see the
damage, then again with --apply once you are satisfied.

    python scripts/repair-phone-numbers.py                 # count only, changes nothing
    python scripts/repair-phone-numbers.py --apply         # perform the repair

Why this is needed separately from the code fix: `normalize_phone` was corrected, but that fixes
INPUT. Values already stored were written by the buggy version, and the new function treats a stored
value as decisive -- '+021555123' starts with '+', so it passes straight through unchanged. Running
the normaliser over the database repairs nothing.

What it fixes:
    021555123       -> +6421555123    a kept national trunk prefix
    +021555123      -> +6421555123    the same, after a '+'
    +646421555123   -> +6421555123    a doubled country code
    095551234       -> +6495551234    a kept landline trunk prefix

What it will NOT touch: emails (legitimate in opt_outs.contact and outbox.to_addr), values that are
already clean, and anything it does not confidently recognise -- those are REPORTED instead, because
rewriting a customer's number wrongly sends messages to a stranger.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from app import db, phone_repair  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description="Repair stored phone numbers")
    parser.add_argument("--apply", action="store_true",
                        help="actually write the repairs (default: count only)")
    args = parser.parse_args()

    await db.init()
    try:
        if not args.apply:
            report = await phone_repair.survey(db.pool())
            print(json.dumps(report, indent=2, default=str))
            total = sum(c["broken"] for c in report["columns"].values())
            human = sum(len(c["needs_human"]) for c in report["columns"].values())
            print(f"\nDRY RUN: {total} value(s) would be repaired. Nothing was changed.")
            if human:
                print(f"{human} value(s) need a human decision (listed above as needs_human).")
            print("Re-run with --apply to perform the repair.")
            return 0

        result = await phone_repair.migrate(db.pool(), dry_run=False)
        print(json.dumps(result, indent=2, default=str))
        total = sum(result["changed"].values())
        print(f"\nAPPLIED: {total} value(s) repaired.")
        for column, values in result["needs_human"].items():
            if values:
                print(f"  still needs a human: {column} -> {values}")
        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
