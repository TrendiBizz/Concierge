"""SMS sending and webhook verification behind one provider switch.

Providers (SMS_PROVIDER):
  twilio   Twilio REST API. Use a Messaging Service SID when the sender is a short code or a pool.
  smsgate  A self-hosted Android phone running capcom6/android-sms-gateway (Apache-2.0). The phone's
           own SIM is the sender, so a real local mobile number works with no short code.
  none     SMS disabled. Queued texts are skipped, not failed.

Everything outside this file (the outbox, the inbound routes) calls send_sms() and sender_ready() and
does not care which provider is behind them.
"""

import base64
import hashlib
import hmac
import time

import httpx

from . import flood_guard
from .config import get_settings


class SmsNotConfigured(RuntimeError):
    pass


class SmsUncertain(RuntimeError):
    """Provider may have accepted the SMS; never automatically resend."""


class SmsRejected(RuntimeError):
    """Provider definitively rejected the request."""


class SmsRateLimited(RuntimeError):
    pass


def provider() -> str:
    return (get_settings().sms_provider or "none").strip().lower()


def sender_ready(tenant: dict | None = None) -> bool:
    """True when this provider has everything it needs to send for this tenant."""
    s = get_settings()
    if (tenant or {}).get("sms_transport") == "device":
        return bool(tenant.get("sms_enabled") and tenant.get("sms_from"))
    name = provider()
    if name == "twilio":
        has_sender = bool(s.twilio_messaging_service_sid or (tenant or {}).get("sms_from") or s.twilio_from_number)
        return bool(s.twilio_account_sid and s.twilio_auth_token and has_sender)
    if name == "smsgate":
        return bool(s.smsgate_base_url and s.smsgate_username and s.smsgate_password)
    return False


async def send_sms(to_e164: str, body: str, from_number: str | None = None, *,
                   tenant: dict | None = None, request_key: str | None = None,
                   outbox_id: int | None = None) -> str:
    """Send one text through the configured provider. Returns the provider's message id (may be empty)."""
    if not flood_guard.memory_allow("sms:recipient", (to_e164 or "").strip(), 10, 600):
        raise SmsRateLimited("Too many texts to this number in 10 minutes")
    if (tenant or {}).get("sms_transport") == "device":
        from . import device_sms
        if not request_key:
            raise SmsNotConfigured("A stable request ID is required for phone SMS")
        if from_number and from_number != tenant.get("sms_from"):
            raise SmsNotConfigured("Phone sender does not belong to this business")
        return await device_sms.enqueue(tenant, to_e164, body, request_key, outbox_id)
    name = provider()
    if name in {"smsgate", "twilio"}:
        from . import sms_delivery
        if not sender_ready(tenant):
            raise SmsNotConfigured("SMS credentials / sender are not configured")
        if outbox_id is not None:
            if not await sms_delivery.begin(outbox_id, tenant["id"], name):
                raise SmsUncertain("SMS already submitted; reconcile before retry")
        try:
            message_id = (await _send_smsgate(to_e164, body) if name == "smsgate" else
                          await _send_twilio(to_e164, body, from_number, outbox_id=outbox_id))
        except SmsRejected:
            raise
        except Exception:
            # A timeout, malformed response or dropped connection can follow acceptance.
            # Keep both logs and the outbox free of credentials/provider response bodies.
            raise SmsUncertain("SMS submission unconfirmed; reconcile before retry") from None
        if outbox_id is not None:
            await sms_delivery.accepted(outbox_id, name, message_id)
        return message_id
    raise SmsNotConfigured("SMS_PROVIDER is not set to a sending provider")


# ---- Twilio ----------------------------------------------------------------
async def _send_twilio(to_e164: str, body: str, from_number: str | None, *, outbox_id: int | None = None) -> str:
    s = get_settings()
    sender = from_number or s.twilio_from_number
    if not (s.twilio_account_sid and s.twilio_auth_token and (sender or s.twilio_messaging_service_sid)):
        raise SmsNotConfigured("Twilio credentials / sender are not configured")
    data = {"To": to_e164, "Body": body[:1500]}
    if s.twilio_messaging_service_sid:
        data["MessagingServiceSid"] = s.twilio_messaging_service_sid
    else:
        data["From"] = sender
    if outbox_id is not None:
        data["StatusCallback"] = s.public_base_url.rstrip("/") + f"/api/v1/sms/status/{outbox_id}"
    url = f"{s.twilio_api_base.rstrip('/')}/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, data=data, auth=(s.twilio_account_sid, s.twilio_auth_token))
    if 400 <= resp.status_code < 500:
        raise SmsRejected("SMS provider rejected submission")
    resp.raise_for_status()
    sid = resp.json().get("sid", "")
    if not sid:
        raise SmsUncertain("SMS submission returned no identifier")
    return sid


def validate_signature(auth_token: str, url: str, params: dict[str, str], signature: str) -> bool:
    """Verify Twilio's X-Twilio-Signature (HMAC-SHA1 of the URL plus sorted POST params)."""
    data = url + "".join(key + params[key] for key in sorted(params))
    mac = hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()
    expected = base64.b64encode(mac).decode()
    return hmac.compare_digest(expected, signature or "")


# ---- Self-hosted Android gateway (capcom6/android-sms-gateway) -------------
def smsgate_payload(to_e164: str, body: str, sim_number: int = 0) -> dict:
    payload: dict = {"textMessage": {"text": body[:1500]}, "phoneNumbers": [to_e164]}
    if sim_number in (1, 2, 3):
        payload["simNumber"] = sim_number
    return payload


async def _send_smsgate(to_e164: str, body: str) -> str:
    s = get_settings()
    if not (s.smsgate_base_url and s.smsgate_username and s.smsgate_password):
        raise SmsNotConfigured("SMS gateway URL / username / password are not configured")
    url = s.smsgate_base_url.rstrip("/") + "/" + s.smsgate_send_path.lstrip("/")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            url,
            json=smsgate_payload(to_e164, body, s.smsgate_sim_number),
            auth=(s.smsgate_username, s.smsgate_password),
        )
    if 400 <= resp.status_code < 500:
        raise SmsRejected("SMS gateway rejected submission")
    resp.raise_for_status()  # acceptance is not confirmed delivery
    message_id = resp.json().get("id")
    if not isinstance(message_id, str) or not message_id:
        raise SmsUncertain("SMS gateway returned no identifier")
    return message_id


def validate_smsgate_signature(
    signing_key: str, raw_body: bytes, timestamp: str, signature: str,
    now: float | None = None, tolerance_seconds: int = 300,
) -> bool:
    """Verify a gateway webhook: HMAC-SHA256 (hex) over the raw body followed by the X-Timestamp
    string, keyed by the signing key from the app's Webhooks settings. Rejects stale timestamps.

    NOTE: confirm the concatenation order against the first real webhook from the phone."""
    if not (signing_key and timestamp and signature):
        return False
    try:
        age = abs((now if now is not None else time.time()) - int(timestamp))
    except ValueError:
        return False
    if age > tolerance_seconds:
        return False
    mac = hmac.new(signing_key.encode(), raw_body + timestamp.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, signature.strip().lower())
