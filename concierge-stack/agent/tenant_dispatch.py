"""Verified LiveKit voice dispatch envelope.

A trusted SIP ingress controller must sign the room, destination, trunk and tenant
binding using a secret NOT available to callers or customer-facing clients.
This module alone does not authenticate SIP ingress or create LiveKit dispatches.
Production multi-tenant routing MUST additionally verify the upstream carrier/trunk,
provision tenant-isolated tool backends, and enforce recipient permissions.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass

_NUMBER = re.compile(r"^\+[1-9][0-9]{6,14}$")
_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")
_MAX_AGE = 120


class DispatchDenied(ValueError):
    """Dispatch missing, expired, altered, or not provisioned."""


@dataclass(frozen=True)
class VoiceBinding:
    tenant_id: str
    destination: str
    trunk_id: str
    room: str


def _payload(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def issue(binding: VoiceBinding, secret: str, now: int | None = None) -> dict:
    """For trusted ingress-controller use ONLY, never expose as a public API."""
    if len(secret.encode()) < 32:
        raise DispatchDenied("Dispatch signing is not configured")
    if (not _ID.fullmatch(binding.tenant_id)
            or not _ID.fullmatch(binding.trunk_id)
            or not _NUMBER.fullmatch(binding.destination)
            or not binding.room or len(binding.room) > 180):
        raise DispatchDenied("Invalid dispatch binding")
    claims = {
        "v": 1, "tenant_id": binding.tenant_id, "destination": binding.destination,
        "trunk_id": binding.trunk_id, "room": binding.room,
        "issued_at": int(time.time() if now is None else now),
    }
    claims["signature"] = hmac.new(secret.encode(), _payload(claims), hashlib.sha256).hexdigest()
    return claims


def verify(
    envelope: str | dict, room: str, destination: str, trunk_id: str,
    provisioned: dict[str, dict], secret: str, now: int | None = None,
) -> VoiceBinding:
    """Validate signed assignment AND authoritative provisioned number/trunk map."""
    if len(secret.encode()) < 32:
        raise DispatchDenied("Dispatch signing is not configured")
    try:
        claims = json.loads(envelope) if isinstance(envelope, str) else envelope
        if not isinstance(claims, dict) or set(claims) != {
            "v", "tenant_id", "destination", "trunk_id", "room", "issued_at", "signature"
        }:
            raise ValueError()
        signature = claims["signature"]
        data = {k: v for k, v in claims.items() if k != "signature"}
        if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{64}", signature):
            raise ValueError()
        if type(claims["issued_at"]) is not int or type(claims["v"]) is not int or claims["v"] != 1:
            raise ValueError()
        if any(not isinstance(data[k], str) for k in ("tenant_id", "destination", "trunk_id", "room")):
            raise ValueError()
        expected = hmac.new(secret.encode(), _payload(data), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        current = int(time.time() if now is None else now)
        if not 0 <= current - claims["issued_at"] <= _MAX_AGE:
            raise ValueError()
        if claims["room"] != room or claims["destination"] != destination or claims["trunk_id"] != trunk_id:
            raise ValueError()
        record = provisioned.get(destination)
        if not isinstance(record, dict) or record.get("tenant_id") != claims["tenant_id"]:
            raise ValueError()
        if record.get("trunk_id") != trunk_id or record.get("enabled") is not True:
            raise ValueError()
        if record.get("telephone_authorized") is not True or record.get("provider_verified") is not True:
            raise ValueError()
        if not _ID.fullmatch(claims["tenant_id"]) or not _ID.fullmatch(trunk_id) or not _NUMBER.fullmatch(destination):
            raise ValueError()
        return VoiceBinding(claims["tenant_id"], destination, trunk_id, room)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise DispatchDenied("Voice dispatch not authorized") from exc


def load_provisioned() -> dict[str, dict]:
    """Static operator-controlled registry, not caller or tenant metadata."""
    path = os.environ.get("VOICE_PROVISIONED_REGISTRY", "")
    if not path:
        raise DispatchDenied("Voice registry not configured")
    try:
        with open(path, encoding="utf-8") as handle:
            registry = json.load(handle)
    except (OSError, ValueError) as exc:
        raise DispatchDenied("Voice registry unavailable") from exc
    if not isinstance(registry, dict):
        raise DispatchDenied("Voice registry invalid")
    return registry


def validate_session(room_name: str, room_metadata: str, sip_destination: str, sip_trunk: str) -> VoiceBinding:
    return verify(
        room_metadata, room_name, sip_destination, sip_trunk, load_provisioned(),
        os.environ.get("VOICE_DISPATCH_SIGNING_KEY", ""),
    )
