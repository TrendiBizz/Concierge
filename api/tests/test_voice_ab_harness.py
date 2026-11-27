"""The A/B harness must measure what it claims, or its numbers cannot be used to pick a provider."""
import asyncio

import pytest
import websockets

import voice_ab_harness as h
from fake_realtime import FakeRealtimeServer


async def run(provider, names):
    async with FakeRealtimeServer() as fake:
        def connect(p):
            return websockets.connect(fake.url(p), open_timeout=5)
        return await h.run_provider(provider, connect, lambda k: h.tone(h.SELFTEST_SECONDS[k]), names)


@pytest.mark.parametrize('provider', ['openai_realtime', 'gemini_live'])
def test_harness_measures_every_scenario_against_the_fake(provider):
    results = asyncio.run(run(provider, None))
    assert 'error' not in results['greeting'] and results['greeting']['first_audio_s'] < 1.5
    assert 0.2 < results['answer']['reply_latency_s'] < 1.5
    barge = results['barge_in']
    assert 'error' not in barge, barge
    # the long answer is 8 s; stopping within half a second proves barge-in cut it, not that it ended
    assert barge['cutoff_after_interrupt_s'] < 0.5
    assert barge['reply_to_interrupt_s'] is not None and barge['reply_to_interrupt_s'] < 2.0
    tool = results['tool']
    assert tool['tool_called'] and tool['name_ok'] and tool['phone_ok']


@pytest.mark.parametrize('provider', ['openai_realtime', 'gemini_live'])
def test_a_provider_that_never_signals_the_interruption_shows_a_long_cutoff(monkeypatch, provider):
    """The metric must be able to fail: a provider that keeps talking over the caller scores badly."""
    import fake_realtime
    monkeypatch.setattr(fake_realtime.Session, 'interrupts', False)
    barge = asyncio.run(run(provider, ['barge_in']))['barge_in']
    assert barge['cutoff_after_interrupt_s'] > 1.0, barge


def test_live_mode_refuses_without_the_spend_flag(capsys):
    import argparse
    args = argparse.Namespace(selftest=False, live=['openai_realtime'], yes_spend=False, only=None, json=None)
    assert asyncio.run(h.main_async(args)) == 2
    assert '--yes-spend' in capsys.readouterr().err


def test_live_mode_refuses_without_keys(monkeypatch, capsys):
    import argparse
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    args = argparse.Namespace(selftest=False, live=['openai_realtime'], yes_spend=True, only=None, json=None)
    assert asyncio.run(h.main_async(args)) == 2
    assert 'OPENAI_API_KEY' in capsys.readouterr().err
