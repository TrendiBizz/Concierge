"""Security and permission boundaries for the complete portal workflow."""
import asyncio
from datetime import date, datetime, timedelta, timezone
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


def test_website_import_does_not_decode_compressed_pages_twice(monkeypatch):
    import gzip
    monkeypatch.setattr(public_fetch, 'public_addresses', AsyncMock(return_value=['1.1.1.1']))
    def transport(request):
        return httpx.Response(200, headers={'content-encoding':'gzip','content-type':'text/html'}, content=gzip.compress(b'<html>Readable public website</html>'))
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            response=await public_fetch.PublicClient(client,'example.com').get('https://example.com/')
            assert response.text=='<html>Readable public website</html>'
            assert 'content-encoding' not in response.headers
    asyncio.run(run())


def test_ingress_owner_notice_survives_scoring_row_reload(monkeypatch):
    from app import automation
    from unittest.mock import AsyncMock
    lead = {'id': 'lead', 'name': '', 'email': 'owner@example.com', 'phone': '', 'channel': 'chat', 'message': 'test', 'created_at': datetime.now(timezone.utc)}
    monkeypatch.setattr(automation.scoring, 'apply', AsyncMock(return_value=dict(lead)))
    monkeypatch.setattr(automation.tasks, 'create_follow_up', AsyncMock())
    monkeypatch.setattr(automation.events, 'emit', lambda *args, **kwargs: None)
    monkeypatch.setattr(automation.events, 'queue_twenty', AsyncMock())
    notice = AsyncMock()
    monkeypatch.setattr(automation, '_owner_alert', notice)
    asyncio.run(automation.on_lead_created({'id': 'tenant', 'name': 'Business'}, {**lead, '_owner_notice_queued': True}))
    notice.assert_not_awaited()


# ---------------------------------------------------------- worldwide booking window

def test_wide_nz_window_yields_slots_across_the_whole_day():
    """08:00-23:00 NZ with 30-minute slots must offer 30 slots, last ending at 23:00.

    This window exists so an enquirer in any timezone can book. NZ is UTC+13, the
    furthest ahead of the major markets, so the window is expressed in NZ wall time
    and the visitor's own location must never shift it.
    """
    tenant={'timezone':'Pacific/Auckland','slot_minutes':30,'min_notice_hours':0,
            'business_hours':{'fri':[['08:00','23:00']]}}
    slots=booking.day_slots(tenant,date(2026,11,13),datetime(2026,11,12,tzinfo=timezone.utc),[])
    nz=booking.ZoneInfo('Pacific/Auckland')
    local=[x.astimezone(nz).strftime('%H:%M') for x in slots]
    assert len(slots)==30, local
    assert local[0]=='08:00' and local[-1]=='22:30', local
    # the last slot must END by the close, not merely start before it
    assert (slots[-1]+timedelta(minutes=30)).astimezone(nz).strftime('%H:%M')=='23:00'


def test_the_same_slot_is_one_instant_whatever_the_visitor_clock_reads():
    """A slot offered at 08:00 NZ is a single instant; foreign clocks only relabel it.

    The bug this guards: computing availability in the enquirer's timezone, which would
    move the business's own hours and hand a New York visitor a different diary.
    """
    tenant={'timezone':'Pacific/Auckland','slot_minutes':30,'min_notice_hours':0,
            'business_hours':{'fri':[['08:00','23:00']]}}
    slots=booking.day_slots(tenant,date(2026,11,13),datetime(2026,11,12,tzinfo=timezone.utc),[])
    first=slots[0]
    nz=booking.ZoneInfo('Pacific/Auckland')
    assert first.astimezone(nz).strftime('%Y-%m-%d %H:%M')=='2026-11-13 08:00'
    for tzname in ('America/New_York','America/Los_Angeles','Europe/London','Asia/Tokyo'):
        # the instant is unchanged; only the label differs
        assert first.astimezone(booking.ZoneInfo(tzname)).astimezone(timezone.utc)==first
    # and no slot leaks outside the configured NZ window
    assert all(s.astimezone(nz).strftime('%H:%M')>='08:00' for s in slots)
    assert all(s.astimezone(nz).strftime('%H:%M')<='22:30' for s in slots)


def test_min_notice_still_excludes_slots_too_soon_under_a_wide_window():
    """A wide window must not defeat the 2-hour lead time."""
    tenant={'timezone':'Pacific/Auckland','slot_minutes':30,'min_notice_hours':2,
            'business_hours':{'fri':[['08:00','23:00']]}}
    # 'now' is noon NZ on the booking day, so everything before 14:00 must be gone
    now=datetime(2026,11,13,12,0,tzinfo=booking.ZoneInfo('Pacific/Auckland')).astimezone(timezone.utc)
    slots=booking.day_slots(tenant,date(2026,11,13),now,[])
    nz=booking.ZoneInfo('Pacific/Auckland')
    local=[x.astimezone(nz).strftime('%H:%M') for x in slots]
    assert local and local[0]=='14:00', local
    assert '13:30' not in local and '08:00' not in local
