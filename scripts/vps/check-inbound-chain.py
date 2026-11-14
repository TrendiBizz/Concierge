"""Report the inbound-email chain for every tenant. Exit 1 if any chain is broken.

Reads the JSON written by check-inbound-chain.sh (the /admin/inbound-readiness response).
"""
import json
import sys


def main(path: str) -> int:
    data = json.load(open(path))
    tenants = data.get("tenants") or []
    bad = 0
    for tenant in tenants:
        ok = bool(tenant.get("ok"))
        # A test business cannot complete the chain (no real owner grants consent); it is a
        # different kind of "not ok" and must not turn the hourly check red. See the 2026-11-15
        # email storm over trendi-fictitious.
        if not ok and not tenant.get("is_test"):
            bad += 1
        blocked = ", ".join(b.get("check", "?") for b in tenant.get("blocked") or []) or "-"
        warned = ", ".join(w.get("check", "?") for w in tenant.get("warnings") or []) or "-"
        label = "OK  " if ok else ("TEST" if tenant.get("is_test") else "FAIL")
        print(f"{label} {tenant.get('slug', '?'):26} "
              f"blocked={blocked:32} warnings={warned}")
        if not ok and tenant.get("is_test"):
            print("      (test tenant: reported, not alerted on)")
        for item in tenant.get("blocked") or []:
            print(f"      -> {item.get('message', '')}")
    print()
    print(f"{bad} of {len(tenants)} tenant chain(s) broken")
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: check-inbound-chain.py <readiness.json>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
