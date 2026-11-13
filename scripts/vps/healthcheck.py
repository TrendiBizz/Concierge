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
    # The vendored Twenty CRM was retired on 2026-11-13: the Studio is the CRM. Its containers are
    # stopped deliberately, so they are not "expected up" any more -- checking them would page
    # every ten minutes about a decision we made on purpose.
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

DEPLOY_GRACE_MINUTES = 10

# Checks that are reported but must never email: they describe a gap somebody outside this repo has to
# close, so a reminder every few hours is noise, not a call to action. `sms:inbound` means the paired
# phone has never POSTed a message to the API; nothing here can change that.
STATUS_ONLY_CHECKS = {"sms:inbound"}


def mailable(problems: dict) -> dict:
    """Drop the checks that describe a gap outside this repo. They are reported, never mailed."""
    return {k: v for k, v in problems.items() if k not in STATUS_ONLY_CHECKS}


def deploying() -> str:
    """The name of a critical container restarted within the grace window, else "".

    A deploy restarts the api container, so public URLs and the API briefly fail. Paging the operator
    for our own deploy is noise that trains them to ignore real alerts: the two FAIL mails at 18:05
    and 18:10 on 13 Nov were exactly this.
    """
    for name in CRITICAL_CONTAINERS:
        if recently_started(name, minutes=DEPLOY_GRACE_MINUTES):
            return name
    return ""


def recently_started(name: str, minutes: int = 10) -> bool:
    """True when the container began after `minutes` ago. Used to tell a deploy from an outage."""
    code, out = run(["docker", "inspect", "-f", "{{.State.StartedAt}}", name], timeout=15)
    if code != 0:
        return False
    try:
        started = datetime.fromisoformat(out.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - started) < timedelta(minutes=minutes)


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
            # A deploy restarts the api container; during those seconds it is "starting", not broken.
            # That used to page as "[Concierge FAIL] container:trendi-api-1" every time we deployed.
            if recently_started(name, minutes=10):
                results.append(_warn(f"container:{name}",
                                     f"{state} (restarted within 10 minutes, still warming)"))
            else:
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
        code, out = run(["docker", "exec", "trendi-postgres-1", "psql", "-U", "postgres",
                         "-d", "concierge", "-tAc", "select count(*) from email_suppressions"])
        suppressed = int(out.strip()) if code == 0 and out.strip().isdigit() else None
        results.append(_ok("email:suppressions", f"{suppressed} address(es) suppressed")
                       if suppressed is not None
                       else _warn("email:suppressions", "could not read the suppression list"))
    return results


def check_sidecar(api_env: dict) -> list[dict]:
    url = (api_env.get("EMAIL_AUTH_URL") or "http://email-auth:8090/verify").rstrip("/")
    health = url[: -len("/verify")] + "/healthz" if url.endswith("/verify") else url + "/healthz"
    code, out = run(["docker", "exec", "trendi-api-1", "python", "-c",
                     f"import urllib.request;print(urllib.request.urlopen('{health}',timeout=3).status)"], timeout=20)
    return [_ok("email-auth:health", "ok") if code == 0 and "200" in out
            else _fail("email-auth:health", out[:160] or "unreachable")]


def check_sms_inbound() -> list[dict]:
    """Is the paired phone actually delivering texts *into* the platform?

    Outbound texts working proves nothing about inbound: the phone polls our queue either way. A
    device whose `inbound_verified_at` is empty has never once delivered a text to us, so a customer
    replying to a message would be talking to nobody — and that is invisible unless we say so.
    """
    sql = ("SELECT count(*) FILTER (WHERE enabled) AS enabled, "
           "count(*) FILTER (WHERE enabled AND inbound_verified_at IS NULL) AS never_verified "
           "FROM sms_devices")
    rc, out = run(["docker", "exec", "trendi-postgres-1", "psql", "-U", "postgres", "-d",
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


def check_crm_capture() -> list[dict]:
    """Does every enquiry that carried contact details also exist as a customer?

    A lead with a phone or email but no customer record is somebody the CRM cannot show: no history,
    no timeline, invisible in Contacts. The booking path did exactly this until it was fixed, so this
    is checked rather than assumed.
    """
    sql = ("SELECT count(*) FROM leads WHERE case_id IS NULL "
           "AND (coalesce(phone,'')<>'' OR coalesce(email,'')<>'')")
    rc, out = run(["docker", "exec", "trendi-postgres-1", "psql", "-U", "postgres", "-d",
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
    results = []
    # Uptime Kuma was removed on 2026-11-12: it had zero monitors configured, so it checked
    # nothing while looking like monitoring. healthcheck.py + the GitHub Actions uptime probe
    # are the real monitors (2026-11-12 system check).
    for name, url, expected in (
        ("aux:hermes", "http://127.0.0.1:8642/health", (200,)),
    ):
        status, _, _ = http(url, timeout=6)
        results.append(_ok(name, f"HTTP {status}") if status in expected
                       else _fail(name, f"HTTP {status}"))
    return results


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
    """
    remind = REMIND_HOURS if remind_hours is None else remind_hours
    new_alerts, reminders, recoveries = [], [], []

    for name, item in problems.items():
        previous = state.get(name, {})
        first_seen = previous.get("first_seen")
        last_sent = previous.get("last_sent")
        key = item["status"]
        if previous.get("key") != key:
            new_alerts.append(item)
            state[name] = {"status": item["status"], "detail": item["detail"], "key": key,
                           "first_seen": first_seen or now.isoformat(), "last_sent": now.isoformat()}
        elif last_sent and now - datetime.fromisoformat(last_sent) > timedelta(hours=remind):
            reminders.append(item)
            state[name].update(last_sent=now.isoformat(), detail=item["detail"])
        else:
            state[name]["status"] = item["status"]
            state[name]["detail"] = item["detail"]

    for name, previous in list(state.items()):
        if name not in problems and previous.get("status") in ("fail", "warn"):
            recoveries.append({"check": name, "was": previous.get("status"),
                               "since": previous.get("first_seen")})
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
    for step in (check_containers, check_public_urls, check_api_internal, check_database, check_host,
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
    try:
        results.extend(check_crm_capture())
    except Exception as exc:  # noqa: BLE001
        results.append(_fail("check:check_crm_capture", str(exc)[:200]))
    try:
        results.extend(check_sms_inbound())
    except Exception as exc:  # noqa: BLE001
        results.append(_fail("check:check_sms_inbound", str(exc)[:200]))

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
                  "token/routing/worker, inbound chain + rejections, email-auth sidecar, Hermes, Kuma."]
        # The label must describe the worst problem in the mail, not just whether anything failed.
        # A warning-only mail used to arrive as "[Concierge FAIL]", which reads as an outage.
        if report["counts"]["fail"]:
            status = "FAIL"
        elif report["counts"]["warn"]:
            status = "WARN"
        else:
            status = "OK"
        subject = f"[Concierge {status}] " + ", ".join(
            list(i["check"] for i in new_alerts) + [f"{len(recoveries)} recovered"])[:120]
        outcome = send_mail(env, subject, "\n".join(lines))
        print(f"{now.strftime('%Y-%m-%dT%H:%M:%SZ')} alert: {subject} -> {outcome} ({len(new_alerts)} new, "
              f"{len(reminders)} reminders, {len(recoveries)} recovered)", file=sys.stderr)

    print(json.dumps({"ok": report["ok"], "counts": report["counts"],
                      "failures": report["failures"], "warnings": report["warnings"]}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
