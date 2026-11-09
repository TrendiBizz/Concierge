"""Connect existing customer phone services to native Grok SIP; never buy numbers."""
from typing import Literal
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from . import channel_authorization, db, phone_relay, phone_sip
from .config import get_settings

router = APIRouter(prefix="/api/v1/phone/managed")


class PhoneSetup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    designated_number: str = Field(pattern=r"^\+[1-9]\d{6,14}$")
    connection: Literal["existing_sip", "existing_twilio", "mobile_forwarding"] = "mobile_forwarding"
    answer_mode: Literal["all_calls", "unanswered"] = "unanswered"
    owner_number: str = Field(pattern=r"^\+[1-9]\d{6,14}$")



async def save_setup(tenant_id, setup):
    return dict(await db.pool().fetchrow(
        "INSERT INTO managed_phone_setups(tenant_id,designated_number,connection,answer_mode,owner_number) "
        "VALUES($1,$2,$3,$4,$5) ON CONFLICT(tenant_id) DO UPDATE SET "
        "designated_number=EXCLUDED.designated_number,connection=EXCLUDED.connection,"
        "answer_mode=EXCLUDED.answer_mode,owner_number=EXCLUDED.owner_number,"
        "status='requested',updated_at=now() RETURNING designated_number,connection,answer_mode,owner_number,status",
        tenant_id, setup.designated_number, setup.connection, setup.answer_mode, setup.owner_number))


def sip_twiml(config):
    root = Element("Response")
    dial = SubElement(root, "Dial", {"answerOnBridge": "true", "timeout": "30", "timeLimit": "600"})
    sip = SubElement(dial, "Sip", {"username": config["sip_username"], "password": config["sip_password"]})
    sip.text = "sip:" + config["number"] + "@sip.voice.x.ai;transport=tls"
    SubElement(root, "Hangup")
    return tostring(root, encoding="unicode")


@router.post("/twilio/{connection_id}")
async def carrier_incoming(connection_id: str, request: Request):
    settings = get_settings()
    if not settings.phone_receptionist_enabled or settings.phone_voice_provider != "grok":
        raise HTTPException(503, "Telephone answering is not active")
    config = phone_sip.connection_config(connection_id)
    account_sid = config.get("carrier_account_sid", "")
    auth_token = config.get("carrier_auth_token", "")
    if not account_sid or not auth_token:
        raise HTTPException(503, "Existing carrier account is not connected")
    body = await request.body()
    if len(body) > 16384:
        raise HTTPException(413, "Carrier event too large")
    # Parse the signed form exactly once and reject duplicate routing fields.
    from urllib.parse import parse_qsl
    try:
        pairs = parse_qsl(body.decode("utf-8"), keep_blank_values=True)
    except UnicodeError:
        raise HTTPException(400, "Invalid carrier event") from None
    params = dict(pairs)
    if len(params) != len(pairs):
        raise HTTPException(400, "Ambiguous carrier event")
    url = phone_relay.external_url("/api/v1/phone/managed/twilio/" + connection_id)
    if request.url.query or not phone_relay.sms.validate_signature(auth_token, url, params, request.headers.get("x-twilio-signature", "")):
        raise HTTPException(403, "Invalid carrier signature")
    if (params.get("AccountSid") != account_sid
            or not phone_relay.CALL_SID.fullmatch(params.get("CallSid", ""))
            or not phone_relay.NUMBER.fullmatch(params.get("To", ""))):
        raise HTTPException(403, "Carrier account or destination mismatch")
    tenant = await db.pool().fetchrow(
        "SELECT t.* FROM tenants t JOIN phone_numbers p ON p.tenant_id=t.id "
        "WHERE p.e164=$1 AND p.enabled AND t.phone_enabled", params["To"])
    if not tenant or not await channel_authorization.is_authorized(tenant["id"], "telephone"):
        raise HTTPException(403, "Telephone number is not activated")
    if (config["tenant"] != tenant["slug"] or config["number"] != params["To"]
            or not all(config.get(k) for k in ("sip_username", "sip_password"))):
        raise HTTPException(403, "Existing account route does not match this business")
    return Response(sip_twiml(config), media_type="application/xml")
