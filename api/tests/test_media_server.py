"""AMI control plane and the media-server actions built on it.

The tests drive a real TCP server speaking AMI framing, so the client is exercised the way the
PBX uses it: login, one action, response, optional events, close.
"""
import asyncio

import pytest

from app import asterisk_ami, call_control


class Settings:
    ami_host = '127.0.0.1'
    ami_port = 5038
    ami_user = 'concierge'
    ami_secret = 'not-a-real-secret'
    asterisk_channel_dial = 'PJSIP/<number>@concierge-reg'


async def fake_ami(*replies, record=None):
    """A one-shot AMI server: answer each action block in order."""
    queue = list(replies)

    async def handler(reader, writer):
        while True:
            block = await read_block(reader)
            if block is None:
                break
            if record is not None:
                record.append(block)
            if 'Action: Login' in block:
                writer.write(b'Response: Success\r\nMessage: Authentication accepted\r\n\r\n')
            elif queue:
                writer.write(queue.pop(0))
            else:
                writer.write(b'Response: Error\r\nMessage: no script left\r\n\r\n')
            await writer.drain()
        writer.close()

    async def read_block(reader):
        lines = []
        while True:
            raw = await reader.readline()
            if not raw:
                return None
            line = raw.decode().rstrip('\r\n')
            if not line:
                return '\n'.join(lines)
            lines.append(line)

    server = await asyncio.start_server(handler, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    return server, asterisk_ami.AmiConfig('127.0.0.1', port, 'concierge', 'secret')


def run(coro):
    return asyncio.run(coro)


def test_login_and_action_round_trip_over_real_framing():
    async def scenario():
        sent = []
        server, config = await fake_ami(
            b'Response: Success\r\nMessage: Channel status will follow\r\n\r\n'
            b'Event: Status\r\nChannel: PJSIP/concierge-reg-00000001\r\nUniqueid: 1.1\r\n\r\n'
            b'Event: StatusComplete\r\nEventList: Complete\r\nListItems: 1\r\n\r\n',
            record=sent)
        try:
            channels = await asterisk_ami.channels(config)
        finally:
            server.close()
            await server.wait_closed()
        assert [c['Channel'] for c in channels] == ['PJSIP/concierge-reg-00000001']
        assert 'Action: Login' in sent[0] and 'Action: Status' in sent[1]
        assert 'Secret: secret' in sent[0]
    run(scenario())


def test_an_action_refusal_becomes_an_error_not_a_silent_failure():
    async def scenario():
        server, config = await fake_ami(b'Response: Error\r\nMessage: Permission denied\r\n\r\n')
        try:
            with pytest.raises(asterisk_ami.AmiError, match='Permission denied'):
                await asterisk_ami.redirect(config, 'PJSIP/x-1', 'business-alpha-takeover')
        finally:
            server.close()
            await server.wait_closed()
    run(scenario())


def test_values_that_would_inject_a_header_are_refused():
    config = asterisk_ami.AmiConfig('127.0.0.1', 5038, 'concierge', 'secret')
    with pytest.raises(asterisk_ami.AmiError):
        run(asterisk_ami.redirect(config, 'PJSIP/x-1', 'ctx\r\nAction: Command'))
    with pytest.raises(asterisk_ami.AmiError):
        run(asterisk_ami.set_variable(config, 'PJSIP/x-1', 'CONCIERGE_TRANSFER', '123\nAction: Command'))
    with pytest.raises(asterisk_ami.AmiError):
        run(asterisk_ami.set_variable(config, 'bad channel name', 'V', '1'))


def test_ami_is_off_unless_host_user_and_secret_are_all_set():
    class Blank(Settings):
        ami_host = ''
    class NoSecret(Settings):
        ami_secret = ''
    assert asterisk_ami.from_settings(Blank()) is None
    assert asterisk_ami.from_settings(NoSecret()) is None
    assert asterisk_ami.from_settings(Settings()).username == 'concierge'


def test_legacy_call_ids_and_spy_modes():
    assert call_control.legacy_call_sid('ast:3f2b8c1e-0000-4000-8000-000000000000') == \
        '3f2b8c1e-0000-4000-8000-000000000000'
    for bad in ('sip:abc', 'ast:not-a-uuid', ''):
        with pytest.raises(call_control.CallControlUnavailable):
            call_control.legacy_call_sid(bad)
    assert call_control.spy_options('listen') == 'qr'
    assert call_control.spy_options('WHISPER') == 'qw'
    assert call_control.spy_options('join') == 'qB'
    with pytest.raises(call_control.CallControlUnavailable):
        call_control.spy_options('eavesdrop')


def test_take_over_sets_the_target_then_redirects_the_caller(monkeypatch):
    async def scenario():
        calls = []

        async def channels(config):
            return [{'Channel': 'PJSIP/concierge-reg-00000002'}]

        async def get_variable(config, channel, variable):
            return '3f2b8c1e-0000-4000-8000-000000000000'

        async def set_variable(config, channel, variable, value):
            calls.append(('setvar', channel, variable, value))

        async def redirect(config, channel, context, exten, priority):
            calls.append(('redirect', channel, context, exten, priority))

        monkeypatch.setattr(call_control.asterisk_ami, 'channels', channels)
        monkeypatch.setattr(call_control.asterisk_ami, 'get_variable', get_variable)
        monkeypatch.setattr(call_control.asterisk_ami, 'set_variable', set_variable)
        monkeypatch.setattr(call_control.asterisk_ami, 'redirect', redirect)
        channel = await call_control.transfer_call(
            'ast:3f2b8c1e-0000-4000-8000-000000000000', 'pukeko-construction', '+64278817368',
            config=Settings())
        assert channel == 'PJSIP/concierge-reg-00000002'
        assert calls == [
            ('setvar', 'PJSIP/concierge-reg-00000002', 'CONCIERGE_TRANSFER', '+64278817368'),
            ('redirect', 'PJSIP/concierge-reg-00000002', 'business-pukeko-construction-takeover',
             's', 1),
        ]
    run(scenario())


def test_supervision_rings_the_owner_and_spies_the_caller(monkeypatch):
    async def scenario():
        originated = []

        async def channels(config):
            return [{'Channel': 'PJSIP/concierge-reg-00000002'}]

        async def get_variable(config, channel, variable):
            return '3f2b8c1e-0000-4000-8000-000000000000'

        async def originate(config, channel, application, data, **kwargs):
            originated.append((channel, application, data))
            return {'Response': 'Success'}

        monkeypatch.setattr(call_control.asterisk_ami, 'channels', channels)
        monkeypatch.setattr(call_control.asterisk_ami, 'get_variable', get_variable)
        monkeypatch.setattr(call_control.asterisk_ami, 'originate', originate)
        await call_control.attach_supervisor(
            'ast:3f2b8c1e-0000-4000-8000-000000000000', '+64278817368', 'whisper',
            channel_dial='PJSIP/<number>@concierge-reg', config=Settings())
        assert originated == [('PJSIP/64278817368@concierge-reg', 'ChanSpy',
                               'PJSIP/concierge-reg-00000002,qw')]
    run(scenario())


def test_an_ended_call_is_refused_rather_than_dialling_the_owner(monkeypatch):
    async def scenario():
        async def channels(config):
            return []

        async def originate(*args, **kwargs):
            raise AssertionError('must not originate for a call that is gone')

        monkeypatch.setattr(call_control.asterisk_ami, 'channels', channels)
        monkeypatch.setattr(call_control.asterisk_ami, 'originate', originate)
        with pytest.raises(call_control.CallControlUnavailable, match='no longer'):
            await call_control.attach_supervisor(
                'ast:3f2b8c1e-0000-4000-8000-000000000000', '+64278817368', 'listen',
                channel_dial='PJSIP/<number>@concierge-reg', config=Settings())
    run(scenario())


def test_an_empty_channel_list_ends_on_quiet_not_on_a_missing_completion_event():
    # Asterisk sends no StatusComplete when there is nothing to list, so waiting
    # for one would hang every console poll on an idle line.
    async def scenario():
        server, config = await fake_ami(b'Response: Success\r\nMessage: Channels listed\r\n\r\n')
        try:
            channels = await asyncio.wait_for(asterisk_ami.channels(config), 3)
        finally:
            server.close()
            await server.wait_closed()
        assert channels == []
    run(scenario())
