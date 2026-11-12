#!/usr/bin/env python3
"""Deep health check for every critical piece of the Concierge stack.

Runs on the VPS from cron every five minutes. It deliberately checks *inside* the box
(containers, database, disk, Cloudflare, the inbound chain) because the external
GitHub Actions check covers "is the box even reachable" from outside.

Alerting sends email through the same Brevo SMTP account the product uses, to
HEALTH_ALERT_TO. Alerts are de-duplicated by check name: one mail when a check goes
bad, a reminder every six hours while it stays bad, and one "recovered" mail.

Exit code 0 = everything healthy, 1 = at least one failure (so cron mail also fires).
Reads secrets from /opt/trendi/shared/api.env and compose.env; never prints them.
"""
from __future__ import annotations

import json
import os
import smtplib
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

API_ENV = Path(os.environ.get("API_ENV", "/opt/trendi/shared/api.env"))
COMPOSE_ENV = Path(os.environ.get("COMPOSE_ENV", "/opt/trendi/shared/compose.env"))
STATE_FILE = Path(os.environ.get("HEALTH_STATE", "/opt/trendi/monitoring/state.json"))
STATUS_FILE = Path(os.environ.get("HEALTH_STATUS", "/opt/trendi/monitoring/status.json"))
ALERT_TO = os.environ.get("HEALTH_ALERT_TO", "kiwi18@gmail.com")
REMIND_HOURS = float(os.environ.get("HEALTH_REMIND_HOURS", "6"))
UA = "trendi-healthcheck/1.0"

# Containers that must be running. "healthy" means the container defines a healthcheck
# and must report healthy; "running" is enough when it has none.
CRITICAL_CONTAINERS = {
    "trendi-postgres-1": "healthy",
    "trendi-api-1": "healthy",
    "trendi-email-auth-1": "healthy",
    "trendi-gateway-1": "running",
    "trendi-media-render-1": "running",
    "trendi-social-1": "running",
    "trendi-website-1": "running",
    "trendi-public-main-1": "running",
    "trendi-public-owner-1": "running",
    "trendi-clamav-1": "healthy",
    "trendi-rspamd-1": "healthy",
    "trendi-crm-1": "healthy",
    "trendi-crm-db-1": "healthy",
    "trendi-crm-redis-1": "running",
    "trendi-crm-worker-1": "running",
    "asterisk-pbx-1": "running",
    "asterisk-bridge-1": "running",
    "trendi-shell-1": "running",
}

# Public URLs a customer or owner would hit. 200 expected unless a list is given.
PUBLIC_URLS = [
    ("https://trendibizz.com/", (200,)),
    ("https://chat.trendibizz.com/demo/pukeko-construction", (200,)),
    ("https://chat.trendibizz.com/widget.js", (200,)),
    ("https://concierge.trendibizz.com/studio/", (200,)),
    ("https://concierge.trendibizz.com/owner-ui", (200,)),
    ("https://crm.trendibizz.com/", (200, 302, 307)),
]

TLS_HOSTS = ["trendibizz.com", "chat.trendibizz.com", "concierge.trendibizz.com", "crm.trendibizz.com"]

DISK_FAIL = 85.0
DISK_WARN = 75.0
MEM_FAIL_MB = 250
LATENCY_FAIL_S = 10.0


def load_env(path: Path) -> dict:
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def run(cmd: list[str], timeout: int = 15) -> tuple[int, str]:
    try:
        finished = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return finished.returncode, (finished.stdout + finished.stderr).strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return 1, str(exc)


def http(url: str, timeout: float = 10.0, headers: dict | None = None, method: str = "GET"):
    request = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})}, method=method)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(4096)
            return response.status, body, time.monotonic() - started
    except urllib.error.HTTPError as exc:
        return exc.code, b"", time.monotonic() - started
    except Exception as exc:  # noqa: BLE001 - any network failure is a failed check
        return 0, str(exc).encode()[:200], time.monotonic() - started


# ---------------------------------------------------------------- individual checks

def check_containers() -> list[dict]:
    results = []
    code, out = run(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}"])
    if code != 0:
        return [_fail("containers", f"docker ps failed: {out[:200]}")]
    status = {}
    for line in out.splitlines():
        name, _, rest = line.partition("\t")
        status[name] = rest
    for name, requirement in CRITICAL_CONTAINERS.items():
        state = status.get(name)
        if state is None:
            results.append(_fail(f"container:{name}", "container missing"))
        elif requirement == "healthy" and "healthy" not in state:
            results.append(_fail(f"container:{name}", state))
        elif "Up" not in state:
            results.append(_fail(f"container:{name}", state))
        else:
            results.append(_ok(f"container:{name}", state))
    return results


def check_public_urls() -> list[dict]:
    results = []
    for url, expected in PUBLIC_URLS:
        status, body, elapsed = http(url)
        name = f"http:{url}"
        if status not in expected:
            results.append(_fail(name, f"HTTP {status} in {elapsed:.2f}s"))
        elif elapsed > LATENCY_FAIL_S:
            results.append(_warn(name, f"slow: {elapsed:.2f}s"))
        else:
            results.append(_ok(name, f"HTTP {status} in {elapsed:.2f}s"))
    return results


def check_api_internal() -> list[dict]:
    results = []
    status, _, elapsed = http("http://127.0.0.1:8000/healthz")
    results.append(_ok("api:healthz", f"HTTP {status} in {elapsed:.2f}s") if status == 200
                   else _fail("api:healthz", f"HTTP {status}"))
    return results


def check_database() -> list[dict]:
    code, out = run(["docker", "exec", "trendi-postgres-1", "psql", "-U", "postgres", "-d", "concierge",
                     "-tAc", "select 1"])
    if code != 0 or out.strip() != "1":
        return [_fail("postgres:query", out[:200] or "no result")]
    results = [_ok("postgres:query", "ok")]
    code, out = run(["docker", "exec", "trendi-postgres-1", "psql", "-U", "postgres", "-d", "concierge",
                     "-tAc", "select count(*) from tenants"])
    if code == 0 and out.strip().isdigit() and int(out.strip()) > 0:
        results.append(_ok("postgres:tenants", f"{out.strip()} tenants"))
    else:
        results.append(_fail("postgres:tenants", out[:120] or "no tenants"))
    return results


def check_host() -> list[dict]:
    results = []
    disk = os.statvfs("/")
    total = disk.f_blocks * disk.f_frsize
    free = disk.f_bavail * disk.f_frsize
    used_pct = (total - free) / total * 100 if total else 0
    name = "host:disk"
    detail = f"{used_pct:.0f}% used, {free / 2**30:.0f}G free"
    results.append(_fail(name, detail) if used_pct >= DISK_FAIL
                   else _warn(name, detail) if used_pct >= DISK_WARN else _ok(name, detail))

    available = None
    try:
        with open("/proc/meminfo") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    available = int(line.split()[1]) / 1024
                    break
    except OSError:
        pass
    if available is None:
        results.append(_warn("host:memory", "MemAvailable unreadable"))
    else:
        results.append(_fail("host:memory", f"{available:.0f}MB available")
                       if available < MEM_FAIL_MB else _ok("host:memory", f"{available:.0f}MB available"))

    load1 = os.getloadavg()[0]
    results.append(_warn("host:load", f"1-min load {load1:.1f}") if load1 > 8 else _ok("host:load", f"{load1:.1f}"))
    return results


def check_cloudflare(api_env: dict) -> list[dict]:
    token = api_env.get("CLOUDFLARE_API_TOKEN") or ""
    zone = api_env.get("CLOUDFLARE_ZONE_ID") or ""
    account = api_env.get("CLOUDFLARE_ACCOUNT_ID") or ""
    worker = api_env.get("CLOUDFLARE_WORKER_NAME") or "concierge-inbound-worker"
    if not token:
        return [_fail("cloudflare:token", "CLOUDFLARE_API_TOKEN missing")]
    auth = {"Authorization": f"Bearer {token}", "content-type": "application/json"}
    results = []

    status, body, _ = http("https://api.cloudflare.com/client/v4/user/tokens/verify", headers=auth)
    results.append(_ok("cloudflare:token", "active") if status == 200 and b"active" in body
                   else _fail("cloudflare:token", f"HTTP {status} {body[:120]!r}"))

    status, body, _ = http(f"https://api.cloudflare.com/client/v4/zones/{zone}/email/routing/rules?per_page=50",
                           headers=auth)
    enabled = 0
    if status == 200:
        try:
            rules = json.loads(body.decode()).get("result") or []
            enabled = sum(1 for rule in rules if rule.get("enabled"))
        except ValueError:
            pass
    results.append(_ok("cloudflare:routing", f"{enabled} enabled rules") if enabled >= 5
                   else _fail("cloudflare:routing", f"HTTP {status}, {enabled} enabled rules (expected >=5)"))

    status, body, _ = http(f"https://api.cloudflare.com/client/v4/accounts/{account}/workers/scripts/{worker}",
                           headers=auth)
    results.append(_ok("cloudflare:worker", worker) if status == 200
                   else _fail("cloudflare:worker", f"HTTP {status} for {worker}"))
    return results


def check_inbound(api_env: dict) -> list[dict]:
    admin = api_env.get("ADMIN_TOKEN") or ""
    if not admin:
        return [_fail("inbound:readiness", "ADMIN_TOKEN missing")]
    results = []
    status, body, _ = http("http://127.0.0.1:8000/admin/inbound-readiness", headers={"X-Admin-Token": admin})
    if status != 200:
        return [_fail("inbound:readiness", f"HTTP {status}")]
    try:
        data = json.loads(body.decode())
    except ValueError:
        return [_fail("inbound:readiness", "unparseable response")]
    broken = [t for t in data.get("tenants") or [] if not t.get("ok")]
    if broken:
        detail = "; ".join(f"{t.get('slug')}: {','.join(b.get('check','?') for b in t.get('blocked') or [])}"
                           for t in broken)
        results.append(_fail("inbound:chain", detail[:400]))
    else:
        results.append(_ok("inbound:chain", f"{len(data.get('tenants') or [])} tenants green"))

    code, out = run(["docker", "exec", "trendi-postgres-1", "psql", "-U", "postgres", "-d", "concierge",
                     "-tAc", "select count(*) from inbound_audit where action='inbound_rejected' "
                             "and created_at > now() - interval '1 hour' "
                             # Bounces are not customer mail: Brevo delivers DSNs to the tenant
                             # reply address, and a report that counts them as refusals cries
                             # wolf every time an address goes bad. They still get audited.
                             "and coalesce(detail->>'sender','') not like 'bounces-%' "
                             "and coalesce(detail->>'sender','') not like 'mailer-daemon@%' "
                             "and coalesce(detail->>'sender','') not like 'postmaster@%'"])
    count = int(out.strip()) if code == 0 and out.strip().isdigit() else None
    if count is None:
        results.append(_warn("inbound:rejections", "could not count rejections"))
    elif count:
        results.append(_fail("inbound:rejections", f"{count} refused in the last hour"))
    else:
        results.append(_ok("inbound:rejections", "none in the last hour"))
    return results


def check_sidecar(api_env: dict) -> list[dict]:
    url = (api_env.get("EMAIL_AUTH_URL") or "http://email-auth:8090/verify").rstrip("/")
    health = url[: -len("/verify")] + "/healthz" if url.endswith("/verify") else url + "/healthz"
    code, out = run(["docker", "exec", "trendi-api-1", "python", "-c",
                     f"import urllib.request;print(urllib.request.urlopen('{health}',timeout=3).status)"], timeout=20)
    return [_ok("email-auth:health", "ok") if code == 0 and "200" in out
            else _fail("email-auth:health", out[:160] or "unreachable")]


def check_tls() -> list[dict]:
    import socket
    results = []
    for host in TLS_HOSTS:
        try:
            context = ssl.create_default_context()
            with socket.create_connection((host, 443), timeout=8) as sock:
                with context.wrap_socket(sock, server_hostname=host) as tls:
                    not_after = tls.getpeercert().get("notAfter", "")
            expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            days = (expiry - datetime.now(timezone.utc)).days
            name = f"tls:{host}"
            results.append(_fail(name, f"certificate expires in {days} days") if days < 7
                           else _warn(name, f"expires in {days} days") if days < 21
                           else _ok(name, f"expires in {days} days"))
        except Exception as exc:  # noqa: BLE001
            results.append(_fail(f"tls:{host}", str(exc)[:120]))
    return results


def check_local_services() -> list[dict]:
    results = []
    for name, url, expected in (
        ("aux:hermes", "http://127.0.0.1:8642/health", (200,)),
        ("aux:kuma", "http://127.0.0.1:3001/", (200, 302)),
    ):
        status, _, _ = http(url, timeout=6)
        results.append(_ok(name, f"HTTP {status}") if status in expected
                       else _fail(name, f"HTTP {status}"))
    return results


# ------------------------------------------------------------------------ plumbing

def _ok(name: str, detail: str) -> dict:
    return {"check": name, "status": "ok", "detail": detail}


def _warn(name: str, detail: str) -> dict:
    return {"check": name, "status": "warn", "detail": detail}


def _fail(name: str, detail: str) -> dict:
    return {"check": name, "status": "fail", "detail": detail}


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))


def send_mail(env: dict, subject: str, body: str) -> str:
    host = env.get("SMTP_HOST", "")
    user = env.get("SMTP_USER", "")
    password = env.get("SMTP_PASSWORD", "")
    sender = env.get("SMTP_FROM", user)
    if not (host and user and password):
        return "SMTP not configured"
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ALERT_TO
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(host, int(env.get("SMTP_PORT") or 25), timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(user, password)
            smtp.send_message(message)
        return "sent"
    except Exception as exc:  # noqa: BLE001 - never let alerting crash the checker
        return f"send failed: {exc}"


def main() -> int:
    started = time.time()
    api_env = load_env(API_ENV)
    compose_env = load_env(COMPOSE_ENV)
    env = {**compose_env, **api_env}

    results: list[dict] = []
    for step in (check_containers, check_public_urls, check_api_internal, check_database, check_host,
                 check_tls, check_local_services):
        try:
            results.extend(step())
        except Exception as exc:  # noqa: BLE001 - a broken check must not stop the rest
            results.append(_fail(f"check:{step.__name__}", str(exc)[:200]))
    for step, args in ((check_cloudflare, (api_env,)), (check_inbound, (api_env,)), (check_sidecar, (api_env,))):
        try:
            results.extend(step(*args))
        except Exception as exc:  # noqa: BLE001
            results.append(_fail(f"check:{step.__name__}", str(exc)[:200]))

    now = datetime.now(timezone.utc)
    state = load_state()
    problems = {r["check"]: r for r in results if r["status"] in ("fail", "warn")}
    new_alerts, reminders, recoveries = [], [], []

    for name, item in problems.items():
        previous = state.get(name, {})
        first_seen = previous.get("first_seen")
        last_sent = previous.get("last_sent")
        key = f"{item['status']}|{item['detail']}"
        if previous.get("key") != key:
            new_alerts.append(item)
            state[name] = {"status": item["status"], "detail": item["detail"], "key": key,
                           "first_seen": first_seen or now.isoformat(), "last_sent": now.isoformat()}
        elif last_sent and now - datetime.fromisoformat(last_sent) > timedelta(hours=REMIND_HOURS):
            reminders.append(item)
            state[name].update(last_sent=now.isoformat(), detail=item["detail"])
        else:
            state[name]["status"] = item["status"]

    for name, previous in list(state.items()):
        if name not in problems and previous.get("status") in ("fail", "warn"):
            recoveries.append({"check": name, "was": previous.get("status"),
                               "since": previous.get("first_seen")})
            state.pop(name, None)

    report = {
        "checked_at": now.isoformat(),
        "duration_s": round(time.time() - started, 1),
        "ok": not any(r["status"] == "fail" for r in results),
        "counts": {status: sum(1 for r in results if r["status"] == status)
                   for status in ("ok", "warn", "fail")},
        "failures": [r for r in results if r["status"] == "fail"],
        "warnings": [r for r in results if r["status"] == "warn"],
        "checks": results,
    }
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(report, indent=2))
    save_state(state)

    if new_alerts or reminders or recoveries:
        lines = [f"Trendi Concierge health check — {now:%Y-%m-%d %H:%M UTC}", ""]
        if new_alerts:
            lines.append("NEW PROBLEMS")
            lines += [f"  [{i['status'].upper()}] {i['check']}: {i['detail']}" for i in new_alerts]
            lines.append("")
        if reminders:
            lines.append(f"STILL BROKEN (> {REMIND_HOURS:g}h)")
            lines += [f"  [{i['status'].upper()}] {i['check']}: {i['detail']}" for i in reminders]
            lines.append("")
        if recoveries:
            lines.append("RECOVERED")
            lines += [f"  {r['check']} (was {r['was']})" for r in recoveries]
            lines.append("")
        lines += [f"Summary: {report['counts']}",
                  f"Detail: {STATUS_FILE}",
                  "Checks cover: containers, public URLs, API, Postgres, disk/memory, TLS, Cloudflare "
                  "token/routing/worker, inbound chain + rejections, email-auth sidecar, Hermes, Kuma."]
        status = "OK" if report["ok"] else "FAIL"
        subject = f"[Concierge {status}] " + ", ".join(
            list(i["check"] for i in new_alerts) + [f"{len(recoveries)} recovered"])[:120]
        outcome = send_mail(env, subject, "\n".join(lines))
        print(f"alert: {outcome} -> {ALERT_TO} ({len(new_alerts)} new, "
              f"{len(reminders)} reminders, {len(recoveries)} recovered)", file=sys.stderr)

    print(json.dumps({"ok": report["ok"], "counts": report["counts"],
                      "failures": report["failures"], "warnings": report["warnings"]}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
