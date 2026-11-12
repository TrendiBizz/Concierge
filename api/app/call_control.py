"""Real call control on the Asterisk path: take-over, listen-in and whisper.

This is the media server's job, seen from the application side. The PBX holds the caller's
audio, so a supervisor can be joined to the *live media* rather than to a transcript:

* **Take-over** redirects the caller's channel into ``business-<slug>-takeover``, which rings the
  owner through the same carrier trunk and bridges them to the caller. The AI is off the call the
  moment the redirect happens (its AudioSocket leg ends), and an unanswered transfer falls back
  into the assistant instead of hanging up on the caller.
* **Listen-in** rings the owner and runs ``ChanSpy`` on the caller's channel: they hear the call,
  the caller hears nothing.
* **Whisper** is the same leg with ``w``: the owner is audible to the caller only, so they can
  coach a caller without the assistant hearing them.
* **Join** is ``B``: the owner barges into the conversation as a third party.

Caller identity: the AudioSocket bridge cannot see a caller ID (the socket carries audio only),
but the *channel* can — the dialplan writes ``CONCIERGE_CALL``, and the channel's own
``CALLERID(num)`` is available to the PBX. So this module finds the channel by the call's UUID and
lets the PBX do the work.
"""
import logging
import re

from . import asterisk_ami
from .config import get_settings

log = logging.getLogger('concierge.call_control')

#: ChanSpy options per supervisor mode. ``q`` keeps the beep out of the caller's ear;
#: ``r`` makes a listener receive-only, ``w`` whispers only to the caller, ``B`` barges in.
SPY_MODES = {
    'listen': 'qr',
    'whisper': 'qw',
    'join': 'qB',
}
TRANSFER_TIMEOUT = 30
SLUG = re.compile(r'[a-z0-9][a-z0-9-]{0,79}')


class CallControlUnavailable(RuntimeError):
    """AMI is not configured, or the call cannot be acted on."""


def legacy_call_sid(call_sid):
    """``ast:<uuid>`` → the ``CONCIERGE_CALL`` value the dialplan wrote."""
    text = str(call_sid or '')
    if not text.startswith('ast:'):
        raise CallControlUnavailable('That call is not on the Asterisk path')
    identifier = text[4:].strip()
    if not re.fullmatch(r'[0-9a-f-]{36}', identifier):
        raise CallControlUnavailable('Unrecognised call identifier')
    return identifier


def _config():
    config = asterisk_ami.from_settings(get_settings())
    if not config:
        raise CallControlUnavailable(
            'The PBX control plane is not configured (AMI_HOST/AMI_USER/AMI_SECRET)')
    return config


def enabled():
    return asterisk_ami.from_settings(get_settings()) is not None


def spy_options(mode):
    try:
        return SPY_MODES[str(mode).strip().lower()]
    except KeyError:
        raise CallControlUnavailable(f"Unknown supervisor mode: {mode}")


async def channel_for(call_sid, config=None):
    """The PBX channel carrying this call, or ``None`` if it has gone."""
    identifier = legacy_call_sid(call_sid)
    config = config or _config()
    live = await asterisk_ami.channels(config)
    candidates = [event for event in live
                  if (event.get('Channel') or '').strip()
                  and not (event.get('Channel') or '').startswith('AsyncGoto')]
    # Most deployments have one call at a time; checking each channel's marker keeps the
    # mapping exact rather than guessing from order.
    for event in candidates:
        channel = event['Channel'].strip()
        try:
            marker = await asterisk_ami.get_variable(config, channel, 'CONCIERGE_CALL')
        except asterisk_ami.AmiError:
            continue
        if (marker or '').strip() == identifier:
            return channel
    return None


async def transfer_call(call_sid, tenant_slug, number, *, config=None):
    """Hand the caller to a human. Returns the channel the PBX redirected."""
    if not SLUG.fullmatch(str(tenant_slug or '')):
        raise CallControlUnavailable('Unknown business for this call')
    number = str(number or '').strip()
    if not re.fullmatch(r'\+?[0-9]{3,20}', number):
        raise CallControlUnavailable('A valid transfer number is required')
    config = config or _config()
    channel = await channel_for(call_sid, config)
    if not channel:
        raise CallControlUnavailable('That call is no longer on the switchboard')
    await asterisk_ami.set_variable(config, channel, 'CONCIERGE_TRANSFER', number)
    await asterisk_ami.redirect(config, channel, f'business-{tenant_slug}-takeover', 's', 1)
    log.info('take-over redirect: %s → %s', channel, number)
    return channel


async def attach_supervisor(call_sid, number, mode, *, channel_dial, config=None):
    """Ring the owner and join them to the live media in ``mode``.

    ``channel_dial`` is the outbound pattern for the carrier trunk (``PJSIP/<number>@concierge-reg``);
    it is supplied by the caller so this module does not have to hard-code a trunk name.
    """
    options = spy_options(mode)
    number = str(number or '').strip()
    if not re.fullmatch(r'\+?[0-9]{3,20}', number):
        raise CallControlUnavailable('A valid supervisor number is required')
    config = config or _config()
    channel = await channel_for(call_sid, config)
    if not channel:
        raise CallControlUnavailable('That call is no longer on the switchboard')
    dial = str(channel_dial).replace('<number>', number.lstrip('+'))
    if not re.fullmatch(r'[A-Za-z0-9_/.-]{3,200}', dial):
        raise CallControlUnavailable('Unsupported outbound dialling pattern')
    await asterisk_ami.originate(
        config, dial, 'ChanSpy', f'{channel},{options}', timeout_ms=60_000)
    log.info('%s leg opened for %s on %s', mode, number, channel)
    return channel
