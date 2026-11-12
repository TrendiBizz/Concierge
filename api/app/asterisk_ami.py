"""Asterisk Manager Interface: the control plane under the media.

The PBX is where the caller's audio lives (AudioSocket → the Grok bridge). That makes it the
only place that can act on the *call* rather than the conversation: redirect it to a human, or
attach a supervisor's phone to the live media with ``ChanSpy``. This module is the single place
that speaks AMI (the Switchboard's take-over, listen-in and whisper).

The protocol is a plain-text header block per message, terminated by a blank line. Every request
here is one short-lived connection: log in, send one action, read its ``Response``, optionally
collect the events the action emits, close. Call control is a handful of actions an hour, so a
pool would add state for no benefit.

Security notes:

* AMI has no TLS. The listener is not published to the host; it is bound inside the PBX
  container and reachable only on the private Docker networks, using a scoped AMI user
  (``read=call,reporting`` / ``write=call,originate``) and a per-install random secret.
* Values are validated before they are written: AMI is header-based, so a value containing a
  newline would inject a second header. :func:`_clean` refuses that.
* Nothing here logs the secret.
"""
import asyncio
import logging
import re

log = logging.getLogger('concierge.ami')

DEFAULT_TIMEOUT = 8.0
MAX_LINE = 8192
# AMI is header/key-value, so these are the characters we refuse to interpolate.
_UNSAFE = re.compile(r'[\r\n\x00]')


class AmiError(RuntimeError):
    """AMI refused an action, or could not be reached."""


class AmiConfig:
    __slots__ = ('host', 'port', 'username', 'secret')

    def __init__(self, host, port, username, secret):
        self.host, self.port = str(host).strip(), int(port)
        self.username, self.secret = str(username), str(secret)

    def __repr__(self):  # never print the secret
        return f'AmiConfig({self.host}:{self.port}, user={self.username})'


def from_settings(settings):
    """The configured AMI target, or ``None`` when the control plane is off."""
    host = (getattr(settings, 'ami_host', '') or '').strip()
    user = (getattr(settings, 'ami_user', '') or '').strip()
    secret = getattr(settings, 'ami_secret', '') or ''
    if not (host and user and secret):
        return None
    return AmiConfig(host, getattr(settings, 'ami_port', 5038) or 5038, user, secret)


def _clean(name, value, *, pattern=None, allow_empty=False):
    """Reject anything that would break AMI's header framing."""
    text = '' if value is None else str(value)
    if not text and not allow_empty:
        raise AmiError(f'{name} is required')
    if _UNSAFE.search(text):
        raise AmiError(f'{name} contains a control character')
    if pattern is not None and not re.fullmatch(pattern, text):
        raise AmiError(f'{name} is not a valid {name}')
    return text


CHANNEL = r'[A-Za-z0-9_/.-]{1,200}'
VARIABLE = r'[A-Za-z0-9_]{1,64}'
NUMBER = r'\+?[0-9]{3,20}'


async def _read_message(reader, timeout=DEFAULT_TIMEOUT):
    fields = {}
    while True:
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout)
        except asyncio.TimeoutError:
            raise AmiError('AMI did not answer in time')
        if not raw:
            raise AmiError('AMI closed the connection')
        if len(raw) > MAX_LINE:
            raise AmiError('AMI sent an oversized line')
        line = raw.decode('utf-8', 'replace').rstrip('\r\n')
        if not line:
            return fields
        key, _, value = line.partition(':')
        fields[key.strip()] = value.strip()


def _encode(fields):
    """One AMI action as a header block. Order is preserved for readability."""
    lines = [f'{key}: {value}' for key, value in fields.items()]
    return ('\r\n'.join(lines) + '\r\n\r\n').encode('utf-8')


async def action(fields, *, config, events=(), timeout=DEFAULT_TIMEOUT):
    """Run one AMI action and return ``(response, collected_events)``.

    ``events`` names the event types to collect after the response (for example
    ``('CoreShowChannel',)``); collection stops at that action's completion event or timeout.
    """
    if not config:
        raise AmiError('AMI is not configured')
    name = fields.get('Action', 'Action')
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(config.host, config.port), timeout)
    try:
        writer.write(_encode({'Action': 'Login', 'Username': config.username,
                              'Secret': config.secret, 'Events': 'off'}))
        await asyncio.wait_for(writer.drain(), timeout)
        login = await _read_message(reader, timeout)
        if login.get('Response') != 'Success':
            raise AmiError(f"AMI login failed: {login.get('Message') or 'refused'}")
        writer.write(_encode(fields))
        await asyncio.wait_for(writer.drain(), timeout)
        response = await _read_message(reader, timeout)
        collected = []
        wanted = {event.lower() for event in events}
        deadline = asyncio.get_running_loop().time() + timeout
        while wanted:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            message = await _read_message(reader, remaining)
            kind = (message.get('Event') or '').lower()
            if kind in wanted:
                collected.append(message)
            if kind.endswith('complete'):
                break
        if response.get('Response') != 'Success':
            raise AmiError(f"AMI {name} failed: {response.get('Message') or 'refused'}")
        log.debug('AMI %s ok (%s events)', name, len(collected))
        return response, collected
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # the PBX may already have dropped the socket
            pass


async def channels(config, timeout=DEFAULT_TIMEOUT):
    """Every live channel, as AMI reports it."""
    _, events = await action({'Action': 'CoreShowChannels'},
                             config=config, events=('CoreShowChannel',), timeout=timeout)
    return events


async def get_variable(config, channel, variable, timeout=DEFAULT_TIMEOUT):
    channel = _clean('channel', channel, pattern=CHANNEL)
    variable = _clean('variable', variable, pattern=VARIABLE)
    response, _ = await action({'Action': 'Getvar', 'Channel': channel, 'Variable': variable},
                               config=config, timeout=timeout)
    value = response.get('Value')
    if value is None:
        raise AmiError('AMI returned no variable value')
    return value


async def set_variable(config, channel, variable, value, timeout=DEFAULT_TIMEOUT):
    channel = _clean('channel', channel, pattern=CHANNEL)
    variable = _clean('variable', variable, pattern=VARIABLE)
    value = _clean('value', value, allow_empty=True)
    await action({'Action': 'Setvar', 'Channel': channel, 'Variable': variable, 'Value': value},
                 config=config, timeout=timeout)


async def redirect(config, channel, context, exten='s', priority=1, timeout=DEFAULT_TIMEOUT):
    """Send a live channel into another dialplan context — how a human takes a call."""
    channel = _clean('channel', channel, pattern=CHANNEL)
    context = _clean('context', context, pattern=r'[A-Za-z0-9_-]{1,64}')
    exten = _clean('exten', exten, pattern=r'[A-Za-z0-9_+@.-]{1,64}')
    if not isinstance(priority, int) or priority < 1:
        raise AmiError('priority must be a positive integer')
    await action({'Action': 'Redirect', 'Channel': channel, 'Context': context,
                  'Exten': exten, 'Priority': priority}, config=config, timeout=timeout)


async def hangup(config, channel, timeout=DEFAULT_TIMEOUT):
    channel = _clean('channel', channel, pattern=CHANNEL)
    await action({'Action': 'Hangup', 'Channel': channel}, config=config, timeout=timeout)


async def originate(config, channel, application, data, *, caller_id=None, apply_vars=False,
                    timeout_ms=30000, timeout=DEFAULT_TIMEOUT):
    """Ring ``channel`` and, when answered, run ``application`` with ``data`` on that leg.

    This is how a supervisor's phone is joined to a live call: the supervisor leg answers and
    immediately runs ``ChanSpy`` on the caller's channel.
    """
    channel = _clean('channel', channel, pattern=CHANNEL)
    application = _clean('application', application, pattern=r'[A-Za-z0-9_]{1,40}')
    data = _clean('data', data, allow_empty=True)
    fields = {'Action': 'Originate', 'Channel': channel, 'Application': application,
              'Data': data, 'Async': 'true', 'Timeout': str(int(timeout_ms))}
    if apply_vars:
        # Variables set *before* the application runs (Used with Application/Data).
        fields['Variable'] = 'CONCIERGE_SUPERVISOR=1'
    if caller_id:
        fields['CallerID'] = _clean('caller id', caller_id, pattern=r'[^"\r\n]{1,64}')
    response, _ = await action(fields, config=config, timeout=timeout)
    return response
