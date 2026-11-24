"""Connect existing customer phone services to Concierge's Asterisk + Gemini Live bridge; never buy numbers."""
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from . import db

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
