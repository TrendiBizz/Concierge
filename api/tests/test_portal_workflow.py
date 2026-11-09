"""Security and permission boundaries for the complete portal workflow."""
import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx
import pytest
from pydantic import ValidationError
from app import acknowledgements, booking, outbox, owner_notifications, public_fetch, quotations


def test_acknowledgement_dry_run_cannot_mutate(monkeypatch):
    monkeypatch.setattr(acknowledgements.db, 'pool', lambda: pytest.fail('dry run touched database'))
    assert asyncio.run(acknowledgements.request({}, {'requested': False}, {'dry_run': True}))['status'] == 'dry_run'


def test_long_owner_sms_preserves_portal_and_recording_link(monkeypatch):
    monkeypatch.setattr(owner_notifications, 'get_settings', lambda: SimpleNamespace(public_base_url='https://portal.example'))
    link='https://portal.example/recordings/shared/fixture-token'
    result=owner_notifications.sms_body('New voice enquiry', 'Transcript ' * 3000 + '\n' + link)
    assert len(result)<=1400 and link in result and 'https://portal.example/owner-ui' in result


@pytest.mark.parametrize('ip', ['127.0.0.1','10.0.0.1','169.254.169.254','::1','fd00::1'])
def test_import_rejects_private_or_mixed_dns(monkeypatch, ip):
    loop=SimpleNamespace(getaddrinfo=AsyncMock(return_value=[(2,1,6,'',('1.1.1.1',443)),(2,1,6,'',(ip,443))]))
    monkeypatch.setattr(public_fetch.asyncio, 'get_running_loop', lambda: loop)
    with pytest.raises(ValueError, match='public internet'):
        asyncio.run(public_fetch.public_addresses('fixture.example'))


@pytest.mark.parametrize('url',['http://example.com','https://other.example/x','https://user:secret@example.com','https://example.com:8443'])
def test_import_rejects_unsafe_redirect_destination(url):
    async def run():
        async with httpx.AsyncClient() as client:
            with pytest.raises(ValueError):
                await public_fetch.PublicClient(client,'example.com').get(url)
    asyncio.run(run())


def test_calendar_slots_skip_nonexistent_dst_wall_time():
    tenant={'timezone':'Pacific/Auckland','slot_minutes':30,'min_notice_hours':0,'business_hours':{'sun':[['01:00','04:00']]}}
    slots=booking.day_slots(tenant,date(2027,9,26),datetime(2027,9,25,tzinfo=timezone.utc),[])
    local=[x.astimezone(booking.ZoneInfo('Pacific/Auckland')).strftime('%H:%M') for x in slots]
    assert local==['01:00','01:30','03:00','03:30'] and len(set(slots))==len(slots)


@pytest.mark.parametrize('quantity',['NaN','Infinity','-1','0','1.0001'])
def test_quote_rejects_unsupported_quantity(quantity):
    with pytest.raises(ValidationError):
        quotations.QuoteLine(description='Service',quantity=quantity,unit_price_cents=1)


def test_queued_automatic_email_respects_revoked_opt_in(monkeypatch):
    monkeypatch.setattr(outbox,'get_settings',lambda:SimpleNamespace())
    monkeypatch.setattr(outbox.tenants,'get_by_id',AsyncMock(return_value={'id':'a','email_auto_reply':False}))
    finish=AsyncMock();monkeypatch.setattr(outbox,'_finish',finish)
    send=AsyncMock();monkeypatch.setattr(outbox.mailer,'send_email',send)
    asyncio.run(outbox._deliver({'id':1,'tenant_id':'a','kind':'email_secretary_reply','channel':'email'}))
    finish.assert_awaited_once_with(1,'skipped','email_secretary_authorization_revoked');send.assert_not_awaited()


def test_queued_owner_sms_respects_revoked_sms_permission(monkeypatch):
    monkeypatch.setattr(outbox,'get_settings',lambda:SimpleNamespace())
    monkeypatch.setattr(outbox.tenants,'get_by_id',AsyncMock(return_value={'id':'a'}))
    monkeypatch.setattr(outbox.channel_authorization,'is_authorized',AsyncMock(return_value=False))
    finish=AsyncMock();monkeypatch.setattr(outbox,'_finish',finish)
    asyncio.run(outbox._deliver({'id':1,'tenant_id':'a','kind':'owner_alert','channel':'sms'}))
    finish.assert_awaited_once_with(1,'skipped','channel_authorization_missing')
