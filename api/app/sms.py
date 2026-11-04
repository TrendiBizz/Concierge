import base64
import hashlib
import hmac

import httpx

from .config import get_settings


class SmsNotConfigured(RuntimeError):
    pass


async def send_sms(to_e164: str, body: str, from_number: str | None = None) -> str:
    """Send one SMS through Twilio's REST API. Returns Twilio's message SID."""
    s = get_settings()
    sender = from_number or s.twilio_from_number
    if not (s.twilio_account_sid and s.twilio_auth_token and sender):
        raise SmsNotConfigured("Twilio credentials / from number are not configured")
    url = f"{s.twilio_api_base.rstrip('/')}/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            url,
            data={"To": to_e164, "From": sender, "Body": body[:1500]},
            auth=(s.twilio_account_sid, s.twilio_auth_token),
        )
    resp.raise_for_status()
    return resp.json().get("sid", "")


def validate_signature(auth_token: str, url: str, params: dict[str, str], signature: str) -> bool:
    """Verify Twilio's X-Twilio-Signature (HMAC-SHA1 of the URL plus sorted POST params)."""
    data = url + "".join(key + params[key] for key in sorted(params))
    mac = hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()
    expected = base64.b64encode(mac).decode()
    return hmac.compare_digest(expected, signature or "")
