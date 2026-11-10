"""Private Google Calendar connection and durable event/invitation reconciliation.

OAuth uses the already registered owner callback. Secrets remain in the mounted
secret directory, never in API responses, logs, tenant clones or event payloads.
"""
import asyncio
import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from . import db, owner_auth
from .config import get_settings

router = APIRouter(prefix='/owner/calendar', tags=['calendar'])
SCOPES = {'https://www.googleapis.com/auth/calendar.events', 'https://www.googleapis.com/auth/calendar.freebusy'}
API = 'https://www.googleapis.com/calendar/v3'


class CalendarUnavailable(RuntimeError):
    pass


def secret_directory():
    value = get_settings().calendar_credentials_dir
    if not value:
        raise CalendarUnavailable('Calendar connection is not configured')
    return Path(value)


def application():
    try:
        data = json.loads((secret_directory() / 'google-app.json').read_text())
        if not all(data.get(k) for k in ('client_id', 'client_secret', 'redirect_uri')):
            raise ValueError()
        return data
    except (OSError, ValueError):
        raise CalendarUnavailable('Calendar connection is not configured') from None


def token_path(tenant_id):
    return secret_directory() / (str(UUID(str(tenant_id))) + '.json')


def save_token(tenant_id, value):
    path = token_path(tenant_id)
    temporary = path.with_suffix('.' + secrets.token_hex(8) + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


async def connection(tenant_id):
    return await db.pool().fetchrow('SELECT * FROM calendar_connections WHERE tenant_id=$1 AND enabled', tenant_id)


async def access_token(tenant_id):
    try:
        token = json.loads(token_path(tenant_id).read_text())
    except (OSError, ValueError):
        raise CalendarUnavailable('Reconnect the business calendar') from None
    if token.get('expires_at', 0) > datetime.now(timezone.utc).timestamp() + 60:
        return token['access_token']
    app = application()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post('https://oauth2.googleapis.com/token', data={
            'client_id': app['client_id'], 'client_secret': app['client_secret'],
            'refresh_token': token.get('refresh_token', ''), 'grant_type': 'refresh_token'})
    if response.status_code != 200:
        raise CalendarUnavailable('Calendar authorization needs reconnection')
    fresh = response.json()
    token.update(fresh)
    token['expires_at'] = datetime.now(timezone.utc).timestamp() + fresh.get('expires_in', 3600)
    save_token(tenant_id, token)
    return token['access_token']


async def request(tenant_id, method, path, **kwargs):
    token = await access_token(tenant_id)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.request(method, API + path, headers={'Authorization': 'Bearer ' + token}, **kwargs)
    return response


@router.get('')
async def overview(user=Depends(owner_auth.current_user)):
    row = await connection(user['tenant_id'])
    try:
        application()
        configured = True
    except CalendarUnavailable:
        configured = False
    return {'configured': configured, 'connected': bool(row), 'calendar_id': row['calendar_id'] if row else None,
            'provider': 'google', 'note': 'An event and invitation are verified separately for every booking.'}


@router.post('/start')
async def start(user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, 'owner')
    try:
        app = application()
    except CalendarUnavailable as exc:
        raise HTTPException(503, str(exc)) from None
    state = secrets.token_urlsafe(32)
    await db.pool().execute(
        "INSERT INTO calendar_oauth_states(token_hash,tenant_id,user_id) VALUES($1,$2,$3)",
        hashlib.sha256(state.encode()).hexdigest(), user['tenant_id'], user['id'])
    return {'state': state, 'authorization_url': 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
        'client_id': app['client_id'], 'redirect_uri': app['redirect_uri'], 'response_type': 'code',
        'scope': ' '.join(sorted(SCOPES)), 'state': state, 'access_type': 'offline', 'prompt': 'consent'})}


class OAuthFinish(BaseModel):
    state: str = Field(min_length=32, max_length=100)
    code: str = Field(min_length=1, max_length=4096)


@router.post('/finish')
async def finish(body: OAuthFinish, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, 'owner')
    state = await db.pool().fetchval(
        'DELETE FROM calendar_oauth_states WHERE token_hash=$1 AND tenant_id=$2 AND user_id=$3 AND expires_at>now() RETURNING tenant_id',
        hashlib.sha256(body.state.encode()).hexdigest(), user['tenant_id'], user['id'])
    if not state:
        raise HTTPException(409, 'Calendar authorization expired or belongs to another session')
    app = application()
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post('https://oauth2.googleapis.com/token', data={
            'client_id': app['client_id'], 'client_secret': app['client_secret'],
            'redirect_uri': app['redirect_uri'], 'code': body.code, 'grant_type': 'authorization_code'})
    if response.status_code != 200:
        raise HTTPException(400, 'Google rejected calendar authorization; reconnect')
    token = response.json()
    if not SCOPES.issubset(set(token.get('scope', '').split())) or not token.get('refresh_token'):
        raise HTTPException(400, 'Authorize calendar events and availability with offline access')
    token['expires_at'] = datetime.now(timezone.utc).timestamp() + token.get('expires_in', 3600)
    save_token(user['tenant_id'], token)
    await db.pool().execute(
        "INSERT INTO calendar_connections(tenant_id,calendar_id,enabled) VALUES($1,'primary',true) "
        'ON CONFLICT(tenant_id) DO UPDATE SET enabled=true,updated_at=now()', user['tenant_id'])
    return {'connected': True, 'provider': 'google', 'calendar_id': 'primary'}


@router.delete('')
async def disconnect(user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, 'owner')
    await db.pool().execute('UPDATE calendar_connections SET enabled=false,updated_at=now() WHERE tenant_id=$1', user['tenant_id'])
    try:
        token_path(user['tenant_id']).unlink(missing_ok=True)
    except CalendarUnavailable:
        pass
    return {'connected': False}


async def busy(tenant_id, start, end):
    row = await connection(tenant_id)
    if not row:
        return []
    response = await request(tenant_id, 'POST', '/freeBusy', json={
        'timeMin': start.isoformat(), 'timeMax': end.isoformat(), 'items': [{'id': row['calendar_id']}]})
    if response.status_code != 200:
        raise CalendarUnavailable('Calendar availability could not be checked; try again')
    result = response.json().get('calendars', {}).get(row['calendar_id'])
    if result is None or result.get('errors'):
        raise CalendarUnavailable('Business calendar availability is unavailable')
    return [(datetime.fromisoformat(x['start'].replace('Z', '+00:00')), datetime.fromisoformat(x['end'].replace('Z', '+00:00'))) for x in result.get('busy', [])]


def event_id(tenant_id, appointment_id):
    return hashlib.sha256(f'{tenant_id}:{appointment_id}'.encode()).hexdigest()


async def sync_one(appointment_id):
    # One process owns reconciliation for an appointment, including a timed-out insert.
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            appt = await conn.fetchrow('SELECT a.*,t.name AS business_name,t.timezone FROM appointments a JOIN tenants t ON t.id=a.tenant_id WHERE a.id=$1 FOR UPDATE OF a', appointment_id)
            if not appt or not appt['calendar_sync_requested'] or (appt['calendar_state'] == 'synced' and appt['status'] == 'booked'):
                return
            tenant_id = appt['tenant_id']
            calendar = await connection(tenant_id)
            if not calendar:
                await conn.execute("UPDATE appointments SET calendar_state='unconnected',calendar_error='Connect the owner calendar' WHERE id=$1", appointment_id)
                return
            if appt['status'] == 'booked' and (not appt['email'] or not appt['consent_contact']):
                await conn.execute("UPDATE appointments SET calendar_state='needs_contact',calendar_error='Confirm invitation email and permission' WHERE id=$1", appointment_id)
                return
            remote_id = event_id(tenant_id, appointment_id)
            path = '/calendars/' + quote(calendar['calendar_id'], safe='') + '/events'
            try:
                if appt['status'] in ('cancelled', 'no_show'):
                    response = await request(tenant_id, 'DELETE', path + '/' + remote_id, params={'sendUpdates': 'all'})
                    if response.status_code not in (200, 204, 404, 410):
                        raise CalendarUnavailable('Calendar cancellation pending')
                    await conn.execute("UPDATE appointments SET calendar_state='cancelled',calendar_error='' WHERE id=$1", appointment_id)
                    return
                existing = await request(tenant_id, 'GET', path + '/' + remote_id)
                if existing.status_code == 404:
                    conflicts = await busy(tenant_id, appt['starts_at'], appt['ends_at'])
                    if conflicts:
                        await conn.execute("UPDATE appointments SET calendar_state='conflict',calendar_error='Owner calendar has a conflicting event' WHERE id=$1", appointment_id)
                        return
                    payload = {'id': remote_id, 'summary': appt['business_name'] + ' — ' + appt['name'],
                               'description': appt['notes'], 'start': {'dateTime': appt['starts_at'].isoformat(), 'timeZone': appt['timezone']},
                               'end': {'dateTime': appt['ends_at'].isoformat(), 'timeZone': appt['timezone']},
                               'attendees': [{'email': appt['email']}],
                               'extendedProperties': {'private': {'concierge_appointment': str(appointment_id), 'concierge_tenant': str(tenant_id)}}}
                    existing = await request(tenant_id, 'POST', path, params={'sendUpdates': 'all'}, json=payload)
                    if existing.status_code == 409:
                        existing = await request(tenant_id, 'GET', path + '/' + remote_id)
                if existing.status_code not in (200, 201):
                    raise CalendarUnavailable('Calendar provider rejected the event; retry pending')
                result = existing.json()
                emails = {a.get('email', '').lower() for a in result.get('attendees', [])}
                if result.get('status') == 'cancelled' or appt['email'].lower() not in emails or result.get('extendedProperties', {}).get('private', {}).get('concierge_appointment') != str(appointment_id) or result.get('extendedProperties', {}).get('private', {}).get('concierge_tenant') != str(tenant_id):
                    raise CalendarUnavailable('Calendar event or invitation could not be verified')
                for key, expected in (('start', appt['starts_at']), ('end', appt['ends_at'])):
                    actual = datetime.fromisoformat(result[key]['dateTime'].replace('Z', '+00:00'))
                    # Compare to the second, not to the microsecond. Providers do not round-trip
                    # sub-second precision: Google returned 00:30:05 for a stored 00:30:05.917076,
                    # so an exact comparison failed every time and the appointment was stuck in
                    # 'retry' until it exhausted its attempts. The 10-second window is far tighter
                    # than any booking slot, so a genuinely wrong time is still caught.
                    if abs((actual - expected).total_seconds()) >= 10:
                        raise CalendarUnavailable('Calendar event time does not match booking')
                await conn.execute("UPDATE appointments SET calendar_state='synced',calendar_event_id=$2,calendar_error='',calendar_synced_at=now(),invitation_state='provider_requested' WHERE id=$1", appointment_id, remote_id)
            except (CalendarUnavailable, httpx.HTTPError, ValueError, KeyError):
                await conn.execute("UPDATE appointments SET calendar_state='retry',calendar_error='Calendar synchronization pending; retry scheduled',calendar_attempts=calendar_attempts+1,calendar_retry_at=now()+interval '2 minutes' WHERE id=$1", appointment_id)


async def notify_synced(appointment_id):
    from . import automation, tenants
    row = await db.pool().fetchrow("SELECT * FROM appointments WHERE id=$1 AND calendar_state='synced' AND status='booked' AND NOT calendar_notice_done", appointment_id)
    if not row:
        return
    tenant = await tenants.get_by_id(row['tenant_id'])
    lead = await db.pool().fetchrow('SELECT * FROM leads WHERE tenant_id=$1 AND id=$2', row['tenant_id'], row['lead_id'])
    await automation.on_appointment_booked(tenant, dict(row), dict(lead) if lead else None)
    await db.pool().execute('UPDATE appointments SET calendar_notice_done=true WHERE id=$1', appointment_id)


async def process_once():
    rows = await db.pool().fetch("SELECT a.id FROM appointments a JOIN calendar_connections c ON c.tenant_id=a.tenant_id AND c.enabled WHERE a.calendar_sync_requested AND a.ends_at>now() AND ((a.status='booked' AND a.calendar_state IN ('pending','retry','unconnected')) OR (a.status IN ('cancelled','no_show') AND a.calendar_state NOT IN ('cancelled','unconnected','needs_contact'))) AND a.calendar_attempts<10 AND a.calendar_retry_at<=now() ORDER BY a.created_at LIMIT 10")
    for row in rows:
        await sync_one(row['id'])
        await notify_synced(row['id'])
    notices = await db.pool().fetch("SELECT id FROM appointments WHERE calendar_state='synced' AND status='booked' AND NOT calendar_notice_done AND calendar_sync_requested LIMIT 10")
    for row in notices:
        await notify_synced(row['id'])


async def run_forever(stop):
    while not stop.is_set():
        try:
            await process_once()
        except Exception:
            import logging
            logging.getLogger(__name__).warning('Calendar synchronization will retry')
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except asyncio.TimeoutError:
            pass
