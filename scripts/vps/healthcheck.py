#!/usr/bin/env python3
"""Deep health check for every critical piece of the Concierge stack.

Runs on the VPS from cron every five minutes. It deliberately checks *inside* the box
(containers, database, disk, Cloudflare, the inbound chain) because the external
GitHub Actions check covers "is the box even reachable" from outside.

Alerting sends email through the same Brevo SMTP account the product uses, to
HEALTH_ALERT_TO. Alerts are de-duplicated by check name: one mail when a check goes
bad, a reminder every two days while it stays bad, and one "recovered" mail for a failure. A
warning that clears is not announced, and one that comes back inside the reminder window is not
announced again: a flapping warning used to mail on every swing.

Exit code 0 = everything healthy, 1 = at least one failure (so cron mail also fires).
Reads secrets from /opt/trendi/shared/api.env and compose.env; never prints them.
"""
from __future__ import annotations

import hashlib
import json
import re
import os
import smtplib
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

API_ENV = Path(os.environ.get("API_ENV", "/opt/trendi/shared/api.env"))
COMPOSE_ENV = Path(os.environ.get("COMPOSE_ENV", "/opt/trendi/shared/compose.env"))
STATE_FILE = Path(os.environ.get("HEALTH_STATE", "/opt/trendi/monitoring/state.json"))
STATUS_FILE = Path(os.environ.get("HEALTH_STATUS", "/opt/trendi/monitoring/status.json"))
ALERT_TO = os.environ.get("HEALTH_ALERT_TO", "admin@trendibizz.com")
REMIND_HOURS = float(os.environ.get("HEALTH_REMIND_HOURS", "48"))
UA = "trendi-healthcheck/1.0"

# Containers that must be running. "healthy" means the container defines a healthcheck
# and must report healthy; "running" is enough when it has none.
CRITICAL_CONTAINERS = {
    "trendi-postgres-1": "healthy",
    "trendi-api-1": "healthy",
    "trendi-email-auth-1": "healthy",
    "trendi-gateway-1": "running",
    # Standalone social container retired 2026-11-22: social publishing now runs inside trendi-api-1.
    "trendi-website-1": "running",
    "trendi-public-main-1": "running",
    "trendi-public-owner-1": "running",
    # The clamav and rspamd images define no HEALTHCHECK, so "healthy" could never be true; require
    # them up. (Their images were unchanged by the 2026-11-17 Podman move.)
    "trendi-clamav-1": "running",
    "trendi-rspamd-1": "running",
    # The vendored Twenty CRM was retired on 2026-11-13: the Studio is the CRM. Its containers are
    # stopped deliberately, so they are not "expected up" any more -- checking them would page
    # every ten minutes about a decision we made on purpose.
    "asterisk-pbx-1": "running",
    "asterisk-bridge-1": "running",
    "trendi-shell-1": "running",
}

# Public URLs a customer or owner would hit. 200 expected unless a list is given.
SITE = "https://trendibizz.com"

PUBLIC_URLS = [
    ("https://trendibizz.com/", (200,)),
    ("https://chat.trendibizz.com/demo/pukeko-construction", (200,)),
    ("https://chat.trendibizz.com/widget.js", (200,)),
    ("https://chat.trendibizz.com/a2ui-renderer.js", (200,)),
    ("https://concierge.trendibizz.com/studio/", (200,)),
    ("https://concierge.trendibizz.com/owner-ui", (200,)),
]

TLS_HOSTS = ["trendibizz.com", "chat.trendibizz.com", "concierge.trendibizz.com"]

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


# A 4 KB read limit silently truncated JSON bodies. The inbound-readiness payload crossed it on
# 2026-11-16 when one tenant was added (4,757 bytes), and the Cloudflare email-routing rules
# response is bigger than 4 KB whenever it carries real descriptions: both checks reported
# "unparseable"/"0 rules" while the APIs were answering perfectly. Read enough for a JSON
# document; still bounded, because one check must never pull a whole page into memory.
READ_LIMIT = 2_000_000


def http(url: str, timeout: float = 10.0, headers: dict | None = None, method: str = "GET",
         read_limit: int = READ_LIMIT):
    request = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})}, method=method)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(read_limit)
            return response.status, body, time.monotonic() - started
    except urllib.error.HTTPError as exc:
        return exc.code, b"", time.monotonic() - started
    except Exception as exc:  # noqa: BLE001 - any network failure is a failed check
        return 0, str(exc).encode()[:200], time.monotonic() - started


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def redirect_of(url: str, timeout: float = 10.0):
    """(status, Location) for one request, without following the redirect."""
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            return response.status, response.headers.get("Location", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Location", "") if exc.headers else ""
    except Exception:  # noqa: BLE001 - any network failure is a failed check
        return 0, ""


# ---------------------------------------------------------------- individual checks

DEPLOY_GRACE_MINUTES = 10

# Checks that are reported but must never email: they describe a gap somebody outside this repo has to
# close, so a reminder every few hours is noise, not a call to action. `sms:inbound` means the paired
# phone has never POSTed a message to the API; nothing here can change that.
STATUS_ONLY_CHECKS = {"sms:inbound"}

BACKUPS_DIR = os.environ.get("TRENDI_BACKUPS_DIR", "/opt/trendi/backups")
BACKUP_WARN_AFTER_HOURS = 26
BACKUP_FAIL_AFTER_HOURS = 50


def mailable(problems: dict) -> dict:
    """Drop warning-only checks that describe a gap outside this repo; failures still alert."""
    return {
        k: v for k, v in problems.items()
        if not (k in STATUS_ONLY_CHECKS and (v.get("status") if isinstance(v, dict) else "warn") == "warn")
    }


def container_restart_count(name: str) -> int:
    """Return the container's RestartCount (0 on a fresh deploy, >0 on a crash loop)."""
    code, out = run(["podman", "inspect", "-f", "{{.RestartCount}}", name], timeout=15)
    if code != 0:
        return 0
    try:
        return int((out or "0").strip())
    except ValueError:
        return 0


def deploying() -> str:
    """The name of a critical container restarted within the grace window, else "".

    A deploy restarts the api container, so public URLs and the API briefly fail. Paging the operator
    for our own deploy is noise that trains them to ignore real alerts: the two FAIL mails at 18:05
    and 18:10 on 13 Nov were exactly this.

    Never treat a crash-looping container (RestartCount > 0) as a normal deploy: a crash loop keeps
    resetting StartedAt and would otherwise hide behind the grace window indefinitely.
    """
    for name in CRITICAL_CONTAINERS:
        if container_restart_count(name) > 0:
            continue
        if recently_started(name, minutes=DEPLOY_GRACE_MINUTES):
            return name
    return ""


# Podman's `inspect -f '{{.State.StartedAt}}'` prints Go's `time.Time.String()` format
# (`2026-11-21 05:00:00.617192387 +0000 UTC`), not RFC3339 (`2026-11-21T05:00:00.617192387Z`).
# `datetime.fromisoformat` raised ValueError on that string, which made `recently_started()` always
# return False — breaking both the 10-minute startup warming grace and the deploy grace window
# (measured live 2026-11-21 18:00 NZDT).
_CONTAINER_TS_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[T ](?P<time>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<frac>\d+))?"
    r"\s*(?P<tz>Z|[+-]\d{2}:?\d{2})"
)

# Retry briefly when a container is starting or mid-recreate (e.g., the ~2-10s window while
# redeploy-api.sh removes social, recreates api, and reattaches social). Zero delay when all
# containers are already healthy/running.
CONTAINER_RETRY_ATTEMPTS = 3
CONTAINER_RETRY_DELAY_S = 5.0


def parse_container_timestamp(raw: str) -> datetime | None:
    """Parse RFC3339 or Podman/Go `time.Time.String()` container timestamps into UTC."""
    match = _CONTAINER_TS_RE.match((raw or "").strip())
    if not match:
        return None
    tz = match.group("tz")
    if tz == "Z":
        tz = "+00:00"
    elif ":" not in tz:
        tz = f"{tz[:3]}:{tz[3:]}"
    frac = match.group("frac")
    frac_part = f".{frac[:6].ljust(6, '0')}" if frac else ""
    try:
        parsed = datetime.fromisoformat(f"{match.group('date')}T{match.group('time')}{frac_part}{tz}")
    except ValueError:
        return None
    if parsed.year <= 1:
        return None
    return parsed.astimezone(timezone.utc)


def recently_started(name: str, minutes: int = 10) -> bool:
    """True when the container began after `minutes` ago. Used to tell a deploy from an outage."""
    code, out = run(["podman", "inspect", "-f", "{{.State.StartedAt}}", name], timeout=15)
    if code != 0:
        return False
    started = parse_container_timestamp(out)
    if started is None:
        return False
    return (datetime.now(timezone.utc) - started) < timedelta(minutes=minutes)


def _check_containers_once() -> list[dict]:
    results = []
    code, out = run(["podman", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}"])
    if code != 0:
        return [_fail("containers", f"podman ps failed: {out[:200]}")]
    status = {}
    for line in out.splitlines():
        name, _, rest = line.partition("\t")
        status[name] = rest
    for name, requirement in CRITICAL_CONTAINERS.items():
        state = status.get(name)
        if state is None:
            results.append(_fail(f"container:{name}", "container missing"))
        elif requirement == "healthy" and "healthy" not in state:
            # Podman's compat socket does not always append "(healthy)" to the
            # status, so a healthy container would page once it passed the 10-minute warmup. Ask the
            # daemon for the health status directly instead of trusting the ps string. A container
            # whose image defines no health check is "running", which is all that can be required.
            code, health = run(["podman", "inspect", "-f",
                                "{{.State.Running}}|{{.State.Health.Status}}", name], timeout=15)
            running, _, health_status = health.strip().partition("|") if code == 0 else ("", "", "")
            if code == 0 and health_status == "healthy":
                results.append(_ok(f"container:{name}", state + " (healthy)"))
            elif code == 0 and health_status == "" and running == "true":
                results.append(_ok(f"container:{name}", state + " (running; no health check defined)"))
            # A deploy restarts the api container; during those seconds it is "starting", not broken.
            # That used to page as "[Concierge FAIL] container:trendi-api-1" every time we deployed.
            elif recently_started(name, minutes=10):
                results.append(_warn(f"container:{name}",
                                     f"{state} (restarted within 10 minutes, still warming)"))
            else:
                results.append(_fail(f"container:{name}", state))
        elif "Up" not in state:
            results.append(_fail(f"container:{name}", state))
        else:
            results.append(_ok(f"container:{name}", state))
    return results


def check_containers() -> list[dict]:
    attempts = max(1, int(CONTAINER_RETRY_ATTEMPTS))
    results: list[dict] = []
    for attempt in range(attempts):
        results = _check_containers_once()
        if all(item["status"] == "ok" for item in results):
            return results
        if attempt + 1 < attempts and CONTAINER_RETRY_DELAY_S > 0:
            time.sleep(CONTAINER_RETRY_DELAY_S)
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


# The public tool endpoints (site-check, security-check, AI-robots checker). They once broke silently because the
# file serving them was removed and nothing watched them (2026-11-24). tool_endpoints.py is the shared list.
# Every run probes the cheap GETs through the public URL (Cloudflare -> gateway -> API), with the 30 s timeout and
# one retry the inbound check uses. The real engines (one outbound fetch each, limited to 5/hour/IP) run once an
# hour, straight at the API on this box, so the probe never uses a visitor's allowance.
TOOL_FUNCTIONAL_MINUTE_WINDOW = 5   # minutes past the hour in which the hourly engine probe runs


def check_tool_endpoints(now: datetime | None = None) -> list[dict]:
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import tool_endpoints  # next to this file
    results = []
    for endpoint in tool_endpoints.ENDPOINTS:
        ok, detail = tool_endpoints.probe(endpoint, SITE, timeout=INBOUND_READINESS_TIMEOUT,
                                          retry_pause=INBOUND_READINESS_RETRY_PAUSE)
        results.append(_ok(f"tool:{endpoint['name']}", detail) if ok else _fail(f"tool:{endpoint['name']}", detail[:300]))
    if (now or datetime.now(timezone.utc)).minute < TOOL_FUNCTIONAL_MINUTE_WINDOW:
        for endpoint in tool_endpoints.FUNCTIONAL:
            ok, detail = tool_endpoints.probe(endpoint, "http://127.0.0.1:8000", timeout=INBOUND_READINESS_TIMEOUT,
                                              retry_pause=INBOUND_READINESS_RETRY_PAUSE)
            results.append(_ok(f"tool:{endpoint['name']}", detail) if ok else _fail(f"tool:{endpoint['name']}", detail[:300]))
    return results


def check_api_internal() -> list[dict]:
    results = []
    status, _, elapsed = http("http://127.0.0.1:8000/healthz")
    results.append(_ok("api:healthz", f"HTTP {status} in {elapsed:.2f}s") if status == 200
                   else _fail("api:healthz", f"HTTP {status}"))
    return results


def check_database() -> list[dict]:
    code, out = run(["podman", "exec", "trendi-postgres-1", "psql", "-U", "postgres", "-d", "concierge",
                     "-tAc", "select 1"])
    if code != 0 or out.strip() != "1":
        return [_fail("postgres:query", out[:200] or "no result")]
    results = [_ok("postgres:query", "ok")]
    code, out = run(["podman", "exec", "trendi-postgres-1", "psql", "-U", "postgres", "-d", "concierge",
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
    parse_error = ""
    if status == 200:
        try:
            rules = json.loads(body.decode()).get("result") or []
            enabled = sum(1 for rule in rules if rule.get("enabled"))
        except ValueError:
            # Never report "0 enabled rules" for a body we could not read: that sends the operator
            # to Cloudflare looking for deleted rules when the fault is here.
            parse_error = f"unparseable response ({len(body)} bytes)"
    if parse_error:
        results.append(_fail("cloudflare:routing", parse_error))
    elif enabled >= 5:
        results.append(_ok("cloudflare:routing", f"{enabled} enabled rules"))
    else:
        results.append(_fail("cloudflare:routing", f"HTTP {status}, {enabled} enabled rules (expected >=5)"))

    status, body, _ = http(f"https://api.cloudflare.com/client/v4/accounts/{account}/workers/scripts/{worker}",
                           headers=auth)
    results.append(_ok("cloudflare:worker", worker) if status == 200
                   else _fail("cloudflare:worker", f"HTTP {status} for {worker}"))
    return results


def chain_split(tenants: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Real breakage, test-tenant noise, and a new tenant still being onboarded.

    A deliberately fictitious business has no real owner to authorise email read, so it can never
    complete the inbound chain. That is not an operational failure: on 2026-11-15 it mailed
    "trendi-fictitious: consent" every hour and buried the alerts that mattered.

    A real tenant created minutes ago is in the same position for a different reason: no owner has
    signed in yet, so there is no owner account and no consent. Counting that as a failure emailed
    an alert for every new customer from the moment they were created (2026-11-16). Onboarding is
    reported as a warning and becomes a failure when the grace window expires.
    """
    broken = [t for t in tenants if not t.get("ok")]
    return ([t for t in broken if not t.get("is_test") and not t.get("is_new")],
            [t for t in broken if t.get("is_test")],
            [t for t in broken if t.get("is_new") and not t.get("is_test")])


# /admin/inbound-readiness runs a live probe per tenant and takes 7.4-8.8 s on the box (measured
# 2026-11-24, 8 tenants), so the old 10 s default left 1-2 s of headroom: any slow moment turned into
# "HTTP 0" and a mail (17 times since 2026-11-13). Allow 30 s, and retry once before calling it a failure.
INBOUND_READINESS_TIMEOUT = 30.0
INBOUND_READINESS_RETRY_PAUSE = 5.0


def read_inbound_readiness(admin: str) -> tuple[int, bytes]:
    url = "http://127.0.0.1:8000/admin/inbound-readiness"
    status, body, _ = http(url, timeout=INBOUND_READINESS_TIMEOUT, headers={"X-Admin-Token": admin})
    if status == 0:  # no HTTP answer at all: one retry rules out a single dropped/slow request
        time.sleep(INBOUND_READINESS_RETRY_PAUSE)
        status, body, _ = http(url, timeout=INBOUND_READINESS_TIMEOUT, headers={"X-Admin-Token": admin})
    return status, body


def check_inbound(api_env: dict) -> list[dict]:
    admin = api_env.get("ADMIN_TOKEN") or ""
    if not admin:
        return [_fail("inbound:readiness", "ADMIN_TOKEN missing")]
    results = []
    status, body = read_inbound_readiness(admin)
    if status != 200:
        # Status 0 means urllib raised (timeout, refused, reset); `body` then holds the reason.
        reason = f": {body.decode(errors='replace')[:120]}" if status == 0 and body else ""
        return [_fail("inbound:readiness", f"HTTP {status}{reason}")]
    try:
        data = json.loads(body.decode())
    except ValueError:
        return [_fail("inbound:readiness", "unparseable response")]
    tenants = data.get("tenants") or []
    live_broken, test_broken, onboarding = chain_split(tenants)
    broken = live_broken + test_broken + onboarding
    note = ("" if not test_broken
            else " (" + ", ".join(f"{t.get('slug')} is a test tenant" for t in test_broken) + ")")
    if live_broken:
        detail = "; ".join(f"{t.get('slug')}: {','.join(b.get('check','?') for b in t.get('blocked') or [])}"
                           for t in live_broken)
        results.append(_fail("inbound:chain", detail[:400]))
    else:
        green = len(tenants) - len(broken)
        results.append(_ok("inbound:chain", f"{green} tenants green{note}"))

    if onboarding:
        detail = "; ".join(f"{t.get('slug')}: {','.join(b.get('check','?') for b in t.get('blocked') or [])}"
                           for t in onboarding)
        results.append(_warn("inbound:onboarding",
                             f"new tenant still onboarding (fails after the grace window): {detail}"[:400]))

    code, out = run(["podman", "exec", "trendi-postgres-1", "psql", "-U", "postgres", "-d", "concierge",
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

    # Bounce handling (added 2026-11-12). The health check never sends a real event; it proves
    # the wiring: the secret exists, the route survives Caddy's path allowlist, and the
    # suppression table is readable. A dead address with no suppression is the failure that
    # matters, and it is reported as a warning only, because mail can be suppressed by hand.
    if not (api_env.get("BREVO_WEBHOOK_SECRET") or "").strip():
        results.append(_warn("email:bounce-webhook",
                             "BREVO_WEBHOOK_SECRET not set: bounces cannot be ingested"))
    else:
        status, _, _ = http("https://concierge.trendibizz.com/webhooks/brevo")
        # GET returns a small status document; 404 means Caddy's allowlist dropped the path
        # and Brevo could never deliver an event.
        results.append(_ok("email:bounce-webhook", "endpoint routed") if status == 200
                       else _fail("email:bounce-webhook", f"HTTP {status} (expected 200)"))
        code, out = run(["podman", "exec", "trendi-postgres-1", "psql", "-U", "postgres",
                         "-d", "concierge", "-tAc", "select count(*) from email_suppressions"])
        suppressed = int(out.strip()) if code == 0 and out.strip().isdigit() else None
        results.append(_ok("email:suppressions", f"{suppressed} address(es) suppressed")
                       if suppressed is not None
                       else _warn("email:suppressions", "could not read the suppression list"))
    return results


def check_sidecar(api_env: dict) -> list[dict]:
    url = (api_env.get("EMAIL_AUTH_URL") or "http://email-auth:8090/verify").rstrip("/")
    health = url[: -len("/verify")] + "/healthz" if url.endswith("/verify") else url + "/healthz"
    code, out = run(["podman", "exec", "trendi-api-1", "python", "-c",
                     f"import urllib.request;print(urllib.request.urlopen('{health}',timeout=3).status)"], timeout=20)
    results = [_ok("email-auth:health", "ok") if code == 0 and "200" in out
               else _fail("email-auth:health", out[:160] or "unreachable")]

    # Verify the unified built-in social module inside trendi-api-1.
    social_code, social_out = run(
        ["podman", "exec", "trendi-api-1", "python3", "-c",
         "from app import social\n"
         "st = social.config.provider_status()\n"
         "print('enabled=' + str(social.config.is_social_enabled()) + ' providers=' + str(sum(1 for v in st.values() if v)))\n"],
        timeout=20,
    )
    status_text = social_out.strip().splitlines()[-1] if social_out.strip() else ""
    results.append(
        _ok("social:module", status_text)
        if social_code == 0 and "enabled=True" in status_text
        else _fail("social:module", social_out[:160] or "unified social module check failed")
    )
    return results


def check_sms_inbound() -> list[dict]:
    """Is the paired phone actually delivering texts *into* the platform?

    Outbound texts working proves nothing about inbound: the phone polls our queue either way. A
    device whose `inbound_verified_at` is empty has never once delivered a text to us, so a customer
    replying to a message would be talking to nobody — and that is invisible unless we say so.
    """
    sql = ("SELECT count(*) FILTER (WHERE d.enabled) AS enabled, "
           "count(*) FILTER (WHERE d.enabled AND d.inbound_verified_at IS NULL "
           "AND NOT EXISTS (SELECT 1 FROM device_sms_inbound i WHERE i.device_id = d.id)) AS never_verified "
           "FROM sms_devices d "
           "JOIN tenants t ON t.id = d.tenant_id "
           "WHERE NOT COALESCE(t.is_test, false) AND t.sms_enabled AND t.sms_transport = 'device'")
    rc, out = run(["podman", "exec", "trendi-postgres-1", "psql", "-U", "postgres", "-d",
                   "concierge", "-tAc", sql])
    if rc != 0:
        return [_fail("sms:inbound", f"could not read sms_devices: {out.strip()[:80]}")]
    try:
        enabled, never = (int(part) for part in out.strip().split("|"))
    except ValueError:
        return [_fail("sms:inbound", f"unexpected output: {out.strip()[:80]}")]
    if not enabled:
        return [_ok("sms:inbound", "no paired phone in use")]
    if never:
        # A warning, not a failure: nothing is broken, the capability simply has not been exercised.
        # It stays visible in every report and is cleared by one real text.
        return [_warn("sms:inbound",
                      f"{never} of {enabled} paired phone(s) have never delivered a text in; "
                      "send one text to the business number to prove the reply path")]
    return [_ok("sms:inbound", f"{enabled} paired phone(s) delivering")]


# Deactivated/superseded in Stripe on purpose (2026-11-16 and 2026-11-24 $250->199 change); any page still pointing at one dead-ends or misprices buyers.
RETIRED_PAYMENT_LINKS = ("28E8wRbntdSjcsQg7RcEw03", "28EcN7bnt6pRgJ6f3NcEw04", "dRm7sM6GzeDz9he3UA04802")


def site_price_drift(page_html: str, plan_js: str, pages: dict | None = None) -> list[str]:
    """Problems where the published price disagrees with the plan data, or GST is added again.

    On 2026-11-15 the plan data said USD 250/month while hard-coded cards still said $400 and the
    yearly blurb still did arithmetic on the old numbers ("12 months at USD $250 is USD $4,800").
    Prices live in two places — products.js and the cards — so they must be compared, not trusted.
    """
    problems: list[str] = []

    def money(text: str) -> int:
        return int(text.replace(",", ""))

    monthly = re.search(r"monthly:\s*\{\s*price:\s*(\d+)", plan_js)
    yearly = re.search(r"yearly:\s*\{\s*price:\s*(\d+)", plan_js)
    cards = re.findall(r'currency">USD</span>\s*\$([\d,]+)', page_html)

    if monthly and cards:
        expected = money(monthly.group(1))
        card = money(cards[0])
        if card != expected:
            problems.append(f"monthly card says ${card}, plan data says ${expected}")
    if yearly and len(cards) > 1:
        expected = money(yearly.group(1))
        card = money(cards[1])
        if card != expected:
            problems.append(f"yearly card says ${card}, plan data says ${expected}")

    for name, html in (pages or {}).items():
        if re.search(r"\b(?:plus|\+)\s*GST\b|\bGST\s*(?:extra|excluded|added)\b", html, re.IGNORECASE):
            problems.append(f"{name} says GST is added on top; NZ GST must be included in the price")
        for dead in RETIRED_PAYMENT_LINKS:
            if dead in html:
                problems.append(f"{name} links to retired Stripe link {dead}")
        question = "Do prices include tax?"
        if name == "/pricing" and question in html:
            snippet = html.split(question, 1)[1][:600]
            if "include tax" not in snippet and "GST is included" not in snippet:
                problems.append("/pricing tax FAQ is a non-answer; it must say NZ GST is included and non-NZ is 0%")
    return problems


SITE_SENDER_DOMAIN = SITE.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0]
MONEY_PAGES = ("/", "/concierge", "/pricing", "/ai-office", "/ai-office-cost",
               "/after-hours-answering", "/missed-call-text-back", "/ai-chat-widget",
               "/ai-office-clinics", "/ai-office-real-estate",
               "/ai-office-builders", "/ai-office-nz", "/best-ai-office",
               "/virtual-receptionist",
               "/ai-answering-service-vs-human",
               "/ai-visibility", "/security")
# The pages above were renamed from /ai-receptionist*; the old URLs must keep answering with a permanent
# redirect (slash and .html variants too), or every inbound link and ranking signal is lost.
RENAMED_PAGES = {
    "/ai-receptionist": "/ai-office",
    "/ai-receptionist-cost": "/ai-office-cost",
    "/ai-receptionist-clinics": "/ai-office-clinics",
    "/ai-receptionist-real-estate": "/ai-office-real-estate",
    "/ai-receptionist-builders": "/ai-office-builders",
    "/ai-receptionist-nz": "/ai-office-nz",
    "/best-ai-receptionist": "/best-ai-office",
    "/how-does-an-ai-receptionist-work": "/how-does-an-ai-office-work",
}
THIN_PAGE_WORDS = 600
DESCRIPTION_LIMIT = 160

# A bulk "geo" rewrite replaced the country name with "worldwide" across the site on 2026-11-15,
# producing "governed by worldwide law" in the terms, "the worldwide Privacy Act 2020" in the
# privacy policy, an h1 reading "How to choose the best AI receptionist in worldwide", and a
# reported search market of "worldwide" in the sample report. Grammar is the tell.
BROKEN_LOCATION = re.compile(
    r"(?:in|of|from|to|at|for|by) worldwide|worldwide law|worldwide Privacy|<td>worldwide</td>|<h2>worldwide</h2>")


def _parse_head_tags(html: str) -> dict:
    """Parse canonical <link>, <meta name=description|robots>, and <h1> count regardless of attribute order."""
    from html.parser import HTMLParser

    class _HeadParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.canonical: str | None = None
            self.description: str | None = None
            self.robots: str | None = None
            self.h1_count = 0

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            t = tag.lower()
            attr_map = {k.lower(): (v or "") for k, v in attrs}
            if t == "h1":
                self.h1_count += 1
            elif t == "link" and self.canonical is None:
                rels = {r.strip().lower() for r in attr_map.get("rel", "").split()}
                if "canonical" in rels and attr_map.get("href"):
                    self.canonical = attr_map["href"].strip()
            elif t == "meta":
                name = attr_map.get("name", "").strip().lower()
                if name == "description" and self.description is None:
                    self.description = attr_map.get("content", "")
                elif name == "robots" and self.robots is None:
                    self.robots = attr_map.get("content", "")

    parser = _HeadParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    return {
        "canonical": parser.canonical,
        "description": parser.description,
        "robots": parser.robots,
        "h1_count": parser.h1_count,
    }


def page_quality(html: str, minimum_words: int = THIN_PAGE_WORDS) -> list[str]:
    """On-page problems that cost rankings: thin copy, a broken snippet, missing canonical, no h1."""
    problems = []
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    main = body[body.find("<main"):body.find("</main>")] if "<main" in body else body
    words = len(re.findall(r"[A-Za-z0-9']+", re.sub(r"<[^>]+>", " ", main)))
    if words < minimum_words:
        problems.append(f"{words} words (floor {minimum_words})")
    tags = _parse_head_tags(html)
    if tags["h1_count"] != 1:
        problems.append(f"{tags['h1_count']} h1 tags")
    if not tags["canonical"]:
        problems.append("no canonical")
    if tags["description"] is None:
        problems.append("no meta description")
    elif len(tags["description"]) > DESCRIPTION_LIMIT:
        problems.append(f"description {len(tags['description'])} chars (limit {DESCRIPTION_LIMIT})")
    if BROKEN_LOCATION.search(html):
        problems.append("broken location wording")
    return problems


# Brevo's domain authentication publishes brevo1/brevo2 as CNAMEs to its own key hosts, and signs
# with s=brevo1. The first version of this list stopped at "brevo", so on 2026-11-15 it reported
# "no DKIM at any of 13 selectors" while every Brevo message carried dkim=pass d=trendibizz.com.
DKIM_SELECTORS = ("brevo1", "brevo2", "brevo", "mail", "sib", "s1", "s2", "default", "k1",
                  "google", "privateemail", "selector1", "selector2", "smtp", "dkim")


def is_dkim_key(values: list[str]) -> bool:
    """A published DKIM public key, not just a CNAME target line or an unrelated TXT."""
    return any(re.search(r"(?:^|;)\s*p=[A-Za-z0-9+/]{20,}", v.replace(" ", "")) for v in values)


def email_auth_problems(spf: list[str], dmarc: list[str], dkim: list[str],
                        selectors: tuple[str, ...] = DKIM_SELECTORS) -> list[str]:
    """Is this domain allowed to send mail that inboxes will trust?

    On 2026-11-15 the site published `DMARC p=quarantine` while no DKIM record could be found at
    any common selector. A domain that quarantines its own unauthenticated mail sends its own
    invitations to the junk folder, and nothing about open tracking survives that.
    """
    problems: list[str] = []
    spf_txt = " ".join(spf).lower()
    if not spf_txt:
        problems.append("no SPF record")
    elif "v=spf1" not in spf_txt:
        problems.append("SPF record is not a v=spf1 policy")
    dmarc_txt = " ".join(dmarc).lower()
    if not dmarc_txt:
        problems.append("no DMARC record")
    elif "v=dmarc1" in dmarc_txt and "p=none" in dmarc_txt:
        problems.append("DMARC policy is p=none (nothing is enforced)")
    if not dkim:
        problems.append(f"no DKIM record at any of {len(selectors)} selectors")
    return problems


def _txt(name: str) -> list[str]:
    """TXT values for a DNS name, or [] when the resolver is unavailable."""
    try:
        out = subprocess.run(["dig", "+short", "TXT", name], capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return []
    values = []
    for line in (out.stdout or "").splitlines():
        line = line.strip().strip('"')
        if line:
            values.append(line.replace('" "', "").strip('"'))
    return values


def check_email_auth() -> list[dict]:
    """SPF, DMARC and DKIM for the address our mail actually claims to come from."""
    domain = (os.environ.get("MAIL_FROM_DOMAIN") or SITE_SENDER_DOMAIN).strip().lower()
    spf = _txt(domain)
    dmarc = _txt("_dmarc." + domain)
    selector = os.environ.get("SMTP_DKIM_SELECTOR", "").strip()
    selectors = (selector,) + DKIM_SELECTORS if selector else DKIM_SELECTORS
    dkim = []
    for name in selectors:
        if is_dkim_key(_txt(f"{name}._domainkey.{domain}")):
            dkim.append(name)
            break
    problems = email_auth_problems(spf, dmarc, dkim, selectors)
    if problems:
        hint = "" if spf or dmarc else " (DNS lookups returned nothing — is dig installed?)"
        return [_warn("email:auth", f"{domain}: " + "; ".join(problems) + hint)]
    return [_ok("email:auth", f"{domain}: SPF, DMARC and DKIM ({dkim[0]}) all present")]


DEPLOY_MANIFEST = "/opt/trendi/releases/20261108-vps/website/site/.deploy-manifest.json"


def manifest_problems(manifest: dict, actual: dict[str, str]) -> list[str]:
    """Files on the box that disagree with what the last deploy stamped.

    On 2026-11-15 the site was published from a directory that was not a git repository, three
    agents edited it, and 17 files reached production without ever being committed. A manifest
    written at deploy time turns that into something visible: any file that differs from the
    stamped hash, disappears, or appears was changed outside the repo.
    """
    expected = (manifest or {}).get("files") or {}
    if not expected:
        return ["manifest lists no files"]
    problems = []
    missing = sorted(p for p in expected if p not in actual)
    changed = sorted(p for p, digest in expected.items() if p in actual and actual[p] != digest)
    extra = sorted(p for p in actual if p not in expected)
    if missing:
        problems.append(f"{len(missing)} file(s) missing: {', '.join(missing[:3])}")
    if changed:
        problems.append(f"{len(changed)} file(s) changed on the box: {', '.join(changed[:3])}")
    if extra:
        problems.append(f"{len(extra)} file(s) added outside the repo: {', '.join(extra[:3])}")
    return problems


def check_deploy_manifest() -> list[dict]:
    """Compare the deployed site against the manifest the deploy script stamped."""
    site = os.path.dirname(DEPLOY_MANIFEST)
    if not os.path.exists(DEPLOY_MANIFEST):
        return [_warn("deploy:manifest",
                      "the website has no .deploy-manifest.json — it was not published by "
                      "scripts/vps/deploy-site.sh, so production cannot be traced to a commit")]
    try:
        with open(DEPLOY_MANIFEST, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError) as exc:
        return [_fail("deploy:manifest", f"manifest unreadable: {type(exc).__name__}")]
    actual = {}
    for base, _dirs, names in os.walk(site):
        for name in names:
            if name.startswith("._") or name == ".deploy-manifest.json":
                continue
            path = os.path.join(base, name)
            try:
                with open(path, "rb") as handle:
                    actual[os.path.relpath(path, site)] = hashlib.sha256(handle.read()).hexdigest()
            except OSError:
                actual[os.path.relpath(path, site)] = ""
    problems = manifest_problems(manifest, actual)
    if problems:
        return [_fail("deploy:manifest", "; ".join(problems))]
    commit = str(manifest.get("commit") or "?")[:8]
    return [_ok("deploy:manifest", f"{len(manifest['files'])} files match the deploy at {commit}")]


def redirect_target_path(location: str) -> str:
    """The path a Location header points at, whether it is relative or absolute."""
    return urllib.parse.urlsplit(location or "").path


def check_site_pages() -> list[dict]:
    """Fetch the pages that carry the ranking and conversion work and check them for damage.

    Added 2026-11-15 with the content pass: nine commercial pages were under 600 words, ten
    descriptions ran past the snippet, and a rewrite had replaced the jurisdiction with the word
    "worldwide". Nothing watched the site's own pages, so none of it was noticed for days.
    """
    from concurrent.futures import ThreadPoolExecutor
    results: list[dict] = []
    def probe(path: str):
        # A page check needs the whole document: reading the first 4 KB measures the <head>.
        code, body, _ = http(SITE + path, timeout=20.0, read_limit=2_000_000)
        return path, code, body.decode("utf-8", "replace") if code == 200 else ""
    with ThreadPoolExecutor(max_workers=6) as pool:
        pages = list(pool.map(probe, MONEY_PAGES))
    broken = []
    for path, code, html in pages:
        if code != 200:
            broken.append(f"{path} {code}")
            continue
        problems = page_quality(html)
        if problems:
            broken.append(f"{path}: {', '.join(problems)}")
    old_paths = [(old + suffix, new) for old, new in RENAMED_PAGES.items() for suffix in ("", "/")]
    with ThreadPoolExecutor(max_workers=6) as pool:
        hops = list(pool.map(lambda pair: redirect_of(SITE + pair[0], timeout=20.0), old_paths))
    for (old, new), (code, location) in zip(old_paths, hops):
        if redirect_target_path(location) != new or code not in (301, 302):
            broken.append(f"{old} -> {code} {redirect_target_path(location) or '(no redirect)'}, want {new}")
    if broken:
        return [_fail("site:pages", "; ".join(broken)[:400])]
    return [_ok("site:pages", f"{len(pages)} key pages: copy, snippet, canonical and h1 all clean")]


def check_site_seo() -> list[dict]:
    """The deployed site's technical SEO contract: robots policy, sitemap, canonicals, noindex.

    Added with the growth plan. The source tree is guarded before a deploy by
    `scripts/seo/site_seo.py check`, but a deploy is not the only thing that can change what search
    engines see: a proxy rule, a Cloudflare transform or a hand edit on the box all bypass it. This
    checks what is actually served, from the outside, the same way a crawler sees it.

    Fails on: a search or AI-search crawler blocked in robots.txt, a training crawler that stopped
    being blocked, a sitemap URL that does not return 200, a page whose canonical does not match the
    URL it is served at, a page that is noindex while listed in the sitemap, or an IndexNow key that
    does not match the key file the site serves.
    """
    problems: list[str] = []

    # 1. robots.txt keeps search and AI-search crawlers in, training crawlers out.
    code, body, _ = http(f"{SITE}/robots.txt", timeout=15.0, read_limit=200_000)
    if code != 200:
        problems.append(f"robots.txt returned {code}")
    else:
        text = body.decode("utf-8", "replace")
        groups: dict[str, list[str]] = {}
        current: list[str] = []
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            field, value = (part.strip() for part in line.split(":", 1))
            field, value = field.lower(), value.lower()
            if field == "user-agent":
                current = groups.setdefault(value, [])
            elif field in ("allow", "disallow") and current is not None:
                current.append(f"{field}: {value}")
        # Policy changed 2026-11-23 (Jo): the major AI crawlers are allowed so the brand can be discovered.
        for agent in ("googlebot", "bingbot", "oai-searchbot", "perplexitybot", "claude-searchbot",
                      "gptbot", "claudebot", "google-extended", "applebot-extended", "ccbot", "amazonbot"):
            rules = groups.get(agent)
            if rules is None:
                problems.append(f"robots.txt has no {agent} group")
            elif any(rule == "disallow: /" for rule in rules):
                problems.append(f"robots.txt blocks {agent}")
        for agent in ("bytespider",):
            if not any(rule.startswith("disallow: /") for rule in groups.get(agent, [])):
                problems.append(f"robots.txt no longer blocks training crawler {agent}")
        if "sitemap:" not in text.lower():
            problems.append("robots.txt has no Sitemap line")

    # 2. Every URL in the sitemap is served, canonical to itself, and not noindex.
    code, body, _ = http(f"{SITE}/sitemap.xml", timeout=20.0, read_limit=1_000_000)
    urls = re.findall(r"<loc>([^<]+)</loc>", body.decode("utf-8", "replace")) if code == 200 else []
    if code != 200:
        problems.append(f"sitemap.xml returned {code}")
    elif not urls:
        problems.append("sitemap.xml lists no URLs")
    else:
        from concurrent.futures import ThreadPoolExecutor

        def probe(url: str):
            page_code, page_body, _ = http(url, timeout=20.0, read_limit=2_000_000)
            return url, page_code, page_body.decode("utf-8", "replace") if page_code == 200 else ""

        with ThreadPoolExecutor(max_workers=6) as pool:
            for url, page_code, html in pool.map(probe, urls):
                if page_code != 200:
                    problems.append(f"{url} returned {page_code}")
                    continue
                tags = _parse_head_tags(html)
                canonical = tags["canonical"]
                expected = url if url.endswith("/") else url
                if not canonical:
                    problems.append(f"{url} has no canonical")
                elif canonical.rstrip("/") != expected.rstrip("/"):
                    problems.append(f"{url} canonical is {canonical}")
                robots_val = (tags["robots"] or "").lower()
                if "noindex" in robots_val:
                    problems.append(f"{url} is noindex but listed in the sitemap")

    # 3. The public IndexNow key is the key a submission would use.
    code, body, _ = http(f"{SITE}/indexnow-key.json", timeout=15.0, read_limit=10_000)
    if code != 200:
        problems.append(f"indexnow-key.json returned {code}")
    else:
        try:
            key = str(json.loads(body.decode("utf-8", "replace")).get("key") or "")
        except ValueError:
            key = ""
        if not re.fullmatch(r"[0-9a-f]{32}", key):
            problems.append("indexnow-key.json has no valid key")
        else:
            key_code, key_body, _ = http(f"{SITE}/{key}.txt", timeout=15.0, read_limit=1000)
            if key_code != 200 or key_body.decode("utf-8", "replace").strip() != key:
                problems.append(f"IndexNow key file /{key}.txt does not serve the key")

    if problems:
        return [_fail("site:seo", "; ".join(problems)[:400])]
    return [_ok("site:seo",
                f"robots policy holds; {len(urls)} sitemap URLs serve, canonical and indexable; "
                "IndexNow key matches")]


def check_site_data() -> list[dict]:
    """The published dataset must be downloadable and recent enough to keep its promise.

    Added with the growth plan: the crawler research is the site's only piece of original data, and
    the page now tells readers it is refreshed monthly. A dataset page that quietly goes eighteen
    months stale loses the citations it earned and stops being a reason for anyone to link here.
    """
    url = f"{SITE}/research/ai-crawler-blocking-2026"
    code, body, _ = http(url, timeout=20.0, read_limit=2_000_000)
    if code != 200:
        return [_fail("site:data", f"{url} returned {code}")]
    html = body.decode("utf-8", "replace")
    match = re.search(r'"temporalCoverage"\s*:\s*"([0-9]{4}-[0-9]{2}-[0-9]{2})"', html)
    if not match:
        return [_fail("site:data", "the dataset page publishes no temporalCoverage date")]
    try:
        collected = datetime.strptime(match.group(1), "%Y-%m-%d").date()
    except ValueError:
        return [_fail("site:data", f"temporalCoverage {match.group(1)!r} is not a date")]
    age = (datetime.now(timezone.utc).date() - collected).days

    csv_code, csv_body, _ = http(f"{SITE}/research/ai-crawler-blocking-2026/data.csv",
                                 timeout=20.0, read_limit=4_000_000)
    if csv_code != 200:
        return [_fail("site:data", f"the CSV returned {csv_code}")]
    rows = max(0, len(csv_body.splitlines()) - 1)
    if rows < 50:
        return [_fail("site:data", f"the CSV has only {rows} rows; the page claims 100 sites")]

    detail = f"data collected {collected.isoformat()} ({age} days old), {rows} CSV rows"
    if age > 120:
        return [_fail("site:data", detail + " — over four months without a refresh")]
    if age > 45:
        return [_warn("site:data", detail + " — the page promises a monthly refresh")]
    return [_ok("site:data", detail)]


def check_site_prices() -> list[dict]:
    """Published prices must match the plan data, and GST must never appear on the site again.

    Operator decision 2026-11-15: one USD price for everyone, no GST wording anywhere (NZ GST is
    handled inside Stripe). A page that starts talking about GST is the defect this catches.
    """
    status_page, body_page, _ = http(f"{SITE}/concierge")
    status_js, body_js, _ = http(f"{SITE}/products.js")
    if status_page != 200 or status_js != 200:
        return [_warn("site:prices", f"could not read the pricing page (page {status_page}, plans {status_js})")]
    pages = {}
    for path in ("/pricing", "/terms"):
        code, body, _ = http(f"{SITE}{path}")
        if code == 200:
            pages[path] = body.decode("utf-8", "replace")
    problems = site_price_drift(body_page.decode("utf-8", "replace"),
                               body_js.decode("utf-8", "replace"), pages)
    if problems:
        return [_fail("site:prices", "; ".join(problems)[:300])]
    return [_ok("site:prices", "cards match the plan data; no GST wording")]


def check_sip_firewall() -> list[dict]:
    """The rule that keeps the SIP port closed must actually be loaded and owned by a running unit.

    Found inactive on 2026-11-15: trendi-sip-firewall.service was enabled but dead, so the DROP
    rules existed only because the last boot had applied them. A rule flush or a reboot without the
    service would have reopened UDP/5060 to the internet (published container ports bypass ufw).
    """
    code, out = run(["systemctl", "is-active", "trendi-sip-firewall.service"], timeout=15)
    state = out.strip()
    if state != "active":
        return [_fail("sip:firewall", f"trendi-sip-firewall.service is {state or 'unknown'}; "
                                      "UDP/5060 is only closed until the next rule flush")]
    code, rules = run(["iptables", "-S", "TRENDI-SIP"], timeout=15)
    if code != 0 or "DROP" not in rules:
        return [_fail("sip:firewall", "the TRENDI-SIP chain is missing or has no DROP rule")]
    # The chain only matters if traffic is sent through it. Docker consults DOCKER-USER; Podman (netavark) does not, so the
    # jump must also live in FORWARD. A chain that exists but is never jumped to is the same as no firewall.
    for chain in ("FORWARD", "DOCKER-USER"):
        code, jumps = run(["iptables", "-S", chain], timeout=15)
        if code == 0 and "--ctorigdstport 5060" in jumps and "-j TRENDI-SIP" in jumps:
            lines = jumps.splitlines()
            sip = next(i for i, l in enumerate(lines) if "-j TRENDI-SIP" in l)
            accept = next((i for i, l in enumerate(lines) if "-j NETAVARK_FORWARD" in l), None)
            if accept is not None and accept < sip:
                # netavark's FORWARD chain ACCEPTs traffic bound for containers; ahead of our jump it would let SIP through.
                return [_fail("sip:firewall", "NETAVARK_FORWARD is ahead of the TRENDI-SIP jump in FORWARD; "
                                              "SIP is open to the internet until trendi-sip-firewall.service is re-run")]
            return [_ok("sip:firewall", f"service active; TRENDI-SIP ends in DROP and {chain} jumps to it first")]
    return [_fail("sip:firewall", "TRENDI-SIP exists but neither FORWARD nor DOCKER-USER sends UDP/5060 to it; "
                                  "the SIP port is open to the internet")]


def check_backups() -> list[dict]:
    """Is there a recent backup archive, and did the last scheduled run succeed?

    Added 2026-11-15 after the blind spot was measured: encrypted backups stopped on 12 Nov when the
    optional CRM container was stopped, and the health report stayed green for two days because
    nothing looked at backups at all. Fail after two missed daily runs, warn after one.
    """
    archives = sorted(Path(BACKUPS_DIR).glob("trendi-backup-*.tar.gz"),
                      key=lambda path: path.stat().st_mtime)
    results: list[dict] = []
    if not archives:
        results.append(_fail("backup:age", f"no archive in {BACKUPS_DIR}"))
    else:
        newest = archives[-1]
        hours = (time.time() - newest.stat().st_mtime) / 3600
        detail = f"newest {newest.name} is {hours:.1f}h old ({len(archives)} kept)"
        if hours > BACKUP_FAIL_AFTER_HOURS:
            results.append(_fail("backup:age", detail))
        elif hours > BACKUP_WARN_AFTER_HOURS:
            results.append(_warn("backup:age", detail))
        else:
            results.append(_ok("backup:age", detail))
    code, out = run(["systemctl", "is-failed", "trendi-backup.service"], timeout=15)
    state = out.strip().splitlines()[-1] if out.strip() else "unknown"
    if state == "failed":
        results.append(_fail("backup:service", "the last trendi-backup.service run failed"))
    elif state in ("active", "inactive"):
        results.append(_ok("backup:service", f"last scheduled run: {state}"))
    else:
        results.append(_warn("backup:service", f"unexpected backup service state: {state} (rc={code})"))
    return results


def check_crm_capture() -> list[dict]:
    """Does every enquiry that carried contact details also exist as a customer?

    A lead with a phone or email but no customer record is somebody the CRM cannot show: no history,
    no timeline, invisible in Contacts. The booking path did exactly this until it was fixed, so this
    is checked rather than assumed.
    """
    sql = ("SELECT count(*) FROM leads WHERE case_id IS NULL "
           "AND (coalesce(phone,'')<>'' OR coalesce(email,'')<>'')")
    rc, out = run(["podman", "exec", "trendi-postgres-1", "psql", "-U", "postgres", "-d",
                   "concierge", "-tAc", sql])
    if rc != 0:
        return [_fail("crm:capture", f"could not read leads: {out.strip()[:80]}")]
    try:
        orphans = int(out.strip())
    except ValueError:
        return [_fail("crm:capture", f"unexpected output: {out.strip()[:80]}")]
    if orphans:
        return [_fail("crm:capture", f"{orphans} enquiries have contact details but no customer record")]
    return [_ok("crm:capture", "every enquiry with contact details has a customer")]


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
    # Uptime Kuma was removed on 2026-11-12. Concierge handles
    # drafts, tasks and the daily note itself. Nothing here is probed.
    return []


# ------------------------------------------------------------------------ plumbing

def check_outbound_guard(api_env: dict) -> list[dict]:
    """Flood guard: warn when sending is paused, anything was blocked, or volume nears a limit.

    Details never contain counts, so the de-duplicated alert mail fires once per condition, not
    once per run.
    """
    admin = api_env.get("ADMIN_TOKEN") or ""
    if not admin:
        return [_fail("outbound:guard", "ADMIN_TOKEN missing")]
    status, body, _ = http("http://127.0.0.1:8000/admin/outbound/status", headers={"X-Admin-Token": admin})
    if status != 200:
        return [_fail("outbound:guard", f"HTTP {status}")]
    try:
        data = json.loads(body.decode())
    except ValueError:
        return [_fail("outbound:guard", "unparseable response")]
    results = []
    if data.get("paused"):
        results.append(_warn("outbound:paused", "ALL email and text sending is paused (the kill switch is on)"))
    blocked = sorted({f"{b.get('channel')}:{b.get('reason')}" for b in data.get("blocked_last_day") or []})
    if blocked:
        results.append(_warn("outbound:blocked",
                             "the flood guard blocked messages in the last day: " + ", ".join(blocked)[:300]))
    limits = data.get("limits") or {}
    for channel, volume in (data.get("sent") or {}).items():
        cap = (limits.get("global_hour") or {}).get(channel) or 0
        if cap and (volume.get("last_hour") or 0) >= 0.6 * cap:
            results.append(_warn(f"outbound:volume:{channel}",
                                 f"{channel} volume is above 60% of the hourly limit ({cap})"))
    if not results:
        results.append(_ok("outbound:guard", "not paused, nothing blocked, volumes normal"))
    return results


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
    message["X-Concierge-Mail"] = "1"
    message["Auto-Submitted"] = "auto-generated"
    message.set_content(body)
    try:
        with smtplib.SMTP(host, int(env.get("SMTP_PORT") or 25), timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(user, password)
            smtp.send_message(message)
        return "sent"
    except Exception as exc:  # noqa: BLE001 - never let alerting crash the checker
        return f"send failed: {exc}"


def plan_notifications(problems: dict, state: dict, now: datetime,
                       remind_hours: float | None = None) -> tuple[list, list, list]:
    """Decide what to email, mutating `state` in place.

    Pure in the sense that matters: it takes the problems, the stored state and the clock, so it
    can be tested without a live stack. It returns (new alerts, reminders, recoveries).

    Claiming is keyed on the *status*, not the detail. A condition that gets wordier -- for
    example "consent" becoming "consent,mailbox" as another part of the same chain breaks -- is
    still the same problem, and re-emailing every time the wording changes is exactly the noise
    this is meant to avoid. A detail change updates what the next reminder says, silently.

    A failure is only mailed once it has failed on two consecutive runs. The first fail is recorded
    in `state` without `last_sent` ("pending"); the next run that still fails mails it. Blips such
    as a deploy swapping the site for a minute used to send a FAIL and then a RECOVERED mail every
    time. For the same reason a pending fail that clears is dropped silently: the operator never
    heard of it, so telling them it recovered would be the same noise. Warnings mail at once.
    """
    remind = REMIND_HOURS if remind_hours is None else remind_hours
    new_alerts, reminders, recoveries = [], [], []

    for name, item in problems.items():
        previous = state.get(name, {})
        first_seen = previous.get("first_seen")
        last_sent = previous.get("last_sent")
        key = item["status"]
        if previous.get("status") == "cleared" and previous.get("key") == key and last_sent \
                and now - datetime.fromisoformat(last_sent) <= timedelta(hours=remind):
            # A warning that blinked off and on again: the operator already has this one.
            state[name] = {"status": item["status"], "detail": item["detail"], "key": key,
                           "first_seen": first_seen or now.isoformat(), "last_sent": last_sent}
        elif previous.get("key") != key or previous.get("status") == "cleared":
            state[name] = {"status": item["status"], "detail": item["detail"], "key": key,
                           "first_seen": first_seen or now.isoformat(), "last_sent": None}
            if item["status"] == "fail":
                continue  # first fail: pending, mailed only if the next run fails too
            new_alerts.append(item)
            state[name]["last_sent"] = now.isoformat()
        elif item["status"] == "fail" and not last_sent:
            # Second consecutive fail: confirmed.
            new_alerts.append(item)
            state[name].update(detail=item["detail"], last_sent=now.isoformat())
        elif last_sent and now - datetime.fromisoformat(last_sent) > timedelta(hours=remind):
            reminders.append(item)
            state[name].update(last_sent=now.isoformat(), detail=item["detail"])
        else:
            state[name]["status"] = item["status"]
            state[name]["detail"] = item["detail"]

    for name, previous in list(state.items()):
        if name in problems:
            continue
        if previous.get("status") == "fail":
            if previous.get("last_sent"):
                recoveries.append({"check": name, "was": "fail", "since": previous.get("first_seen")})
            state.pop(name, None)  # a never-mailed (pending) fail leaves no trace
        elif previous.get("status") == "warn":
            # Silent: a warning that clears needs no mail. Remember it, so a flap does not re-announce.
            previous["status"] = "cleared"
        elif previous.get("status") == "cleared":
            last_sent = previous.get("last_sent")
            if not last_sent or now - datetime.fromisoformat(last_sent) > timedelta(hours=remind):
                state.pop(name, None)
    return new_alerts, reminders, recoveries


def main(argv: list[str] | None = None) -> int:
    """Run every check. `--no-alert` reports only: no mail, and no change to alert state.

    Manual runs must be side-effect free. Running the check by hand to verify a change used to
    rewrite the state file, which produced spurious "NEW PROBLEMS" and "RECOVERED" mails as the
    state moved under the scheduler's feet.
    """
    args = sys.argv[1:] if argv is None else argv
    alerting = "--no-alert" not in args
    started = time.time()
    api_env = load_env(API_ENV)
    compose_env = load_env(COMPOSE_ENV)
    env = {**compose_env, **api_env}

    results: list[dict] = []
    for step in (check_containers, check_public_urls, check_tool_endpoints, check_api_internal, check_database, check_host,
                 check_tls, check_local_services):
        try:
            results.extend(step())
        except Exception as exc:  # noqa: BLE001 - a broken check must not stop the rest
            results.append(_fail(f"check:{step.__name__}", str(exc)[:200]))
    for step, args in ((check_cloudflare, (api_env,)), (check_inbound, (api_env,)), (check_sidecar, (api_env,)),
                      (check_outbound_guard, (api_env,))):
        try:
            results.extend(step(*args))
        except Exception as exc:  # noqa: BLE001
            results.append(_fail(f"check:{step.__name__}", str(exc)[:200]))
    for step in (check_crm_capture, check_site_prices, check_sms_inbound, check_backups, check_sip_firewall,
                 check_site_pages, check_site_seo, check_site_data, check_email_auth, check_deploy_manifest):
        try:
            results.extend(step())
        except Exception as exc:  # noqa: BLE001 - one broken check must not hide the rest
            results.append(_fail(f"check:{step.__name__}", str(exc)[:200]))

    now = datetime.now(timezone.utc)
    state = load_state()
    problems = {r["check"]: r for r in results if r["status"] in ("fail", "warn")}
    grace = deploying() if alerting else ""
    if grace:
        # Report, but do not mail and do not move the alert state: the "recovery" that follows a deploy
        # is not a recovery, and the failure it paired with was never a fault.
        new_alerts, reminders, recoveries = [], [], []
        print(f"deploy grace: {grace} restarted within {DEPLOY_GRACE_MINUTES} minutes; not alerting",
              file=sys.stderr)
    elif alerting:
        new_alerts, reminders, recoveries = plan_notifications(mailable(problems), state, now)
    else:
        new_alerts, reminders, recoveries = [], [], []

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
    if alerting and not grace:
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
                  "token/routing/worker, inbound chain + rejections, email-auth sidecar."]
        # The label must describe the worst problem in the mail, not just whether anything failed.
        # A warning-only mail used to arrive as "[Concierge FAIL]", which reads as an outage.
        if report["counts"]["fail"]:
            status = "FAIL"
        elif report["counts"]["warn"]:
            status = "WARN"
        else:
            status = "OK"
        parts = [i["check"] for i in new_alerts] + [f"{i['check']} (reminder)" for i in reminders]
        if recoveries:
            parts.append(f"{len(recoveries)} recovered")
        subject = f"[Concierge {status}] " + ", ".join(parts)[:120]
        outcome = send_mail(env, subject, "\n".join(lines))
        print(f"{now.strftime('%Y-%m-%dT%H:%M:%SZ')} alert: {subject} -> {outcome} ({len(new_alerts)} new, "
              f"{len(reminders)} reminders, {len(recoveries)} recovered)", file=sys.stderr)

    summary = {"ok": report["ok"], "counts": report["counts"],
               "failures": report["failures"], "warnings": report["warnings"]}
    if grace:
        summary["deploy_grace"] = grace
    print(json.dumps(summary, indent=2))
    # During an active deploy grace window in scheduled (alerting) mode, exit 0 so cron's
    # `healthcheck.sh || alert.sh` fallback honours the same grace policy instead of emailing on a
    # mid-deploy blip. Manual `--no-alert` runs never enter grace and always exit 1 on failure.
    return 0 if (report["ok"] or grace) else 1


if __name__ == "__main__":
    sys.exit(main())
