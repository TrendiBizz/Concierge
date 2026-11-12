"""Ring the owner first; hand the call to the assistant the moment they decline, are busy or miss it."""
import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "asterisk" / "render_routes.py"
_spec = importlib.util.spec_from_file_location("render_routes_under_test", _PATH)
render_routes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render_routes)

TRUNK = {"server": "sip.hero.co.nz", "username": "092431347", "password": "correct-horse-battery",
         "transport": "udp", "port": 5060}
BASE = {"tenant": "pukeko-construction", "number": "+6492431347", "port": 9510}


def _context(extensions, name):
    lines = extensions.splitlines()
    start = lines.index("[" + name + "]")
    out = []
    for line in lines[start + 1:]:
        if line.startswith("["):
            break
        out.append(line)
    return out


def _render(rows, trunk=TRUNK):
    return render_routes.render(rows, "bridge", "152.42.239.240", trunk)


def test_without_ring_owner_the_dialplan_is_unchanged():
    ext, _ = _render([BASE])
    body = _context(ext, "business-pukeko-construction")
    assert body[0] == "exten => s,1,Answer()"
    assert not any("Dial(" in line for line in body)
    assert body[-1] == " same => n,Hangup()"


def test_ring_owner_dials_first_then_falls_through_to_the_assistant():
    ext, _ = _render([{**BASE, "ring_owner": {"number": "+6421824305", "seconds": 15}}])
    body = _context(ext, "business-pukeko-construction")
    text = "\n".join(body)
    dial = next(i for i, line in enumerate(body) if "Dial(PJSIP/6421824305@concierge-reg,15,r)" in line)
    answer = next(i for i, line in enumerate(body) if "Answer()" in line)
    audio = next(i for i, line in enumerate(body) if "AudioSocket(" in line)
    assert dial < answer < audio  # the caller is only answered once the owner has not picked up
    assert 'GotoIf($["${DIALSTATUS}"="ANSWER"]?done)' in text  # owner answered: no assistant
    assert 'GotoIf($["${DIALSTATUS}"="CANCEL"]?done)' in text  # caller gave up while it rang
    assert body[-1] == " same => n(done),Hangup()"
    assert body.count(" same => n,Hangup()") == 1


def test_only_the_configured_business_rings():
    rows = [{**BASE, "tenant": "a-co", "ring_owner": {"number": "+6421824305"}},
            {"tenant": "b-co", "number": "+6492431348", "port": 9511}]
    ext, _ = _render(rows)
    assert any("Dial(PJSIP/6421824305@concierge-reg,15,r)" in line for line in _context(ext, "business-a-co"))
    assert not any("Dial(" in line for line in _context(ext, "business-b-co"))


@pytest.mark.parametrize("ring", [
    {"number": "6421824305"}, {"number": "+64"}, {"number": "+6421824305", "seconds": 2},
    {"number": "+6421824305", "seconds": 90}, {"number": "+6421824305", "seconds": True}, "+6421824305"])
def test_bad_ring_settings_are_rejected(ring):
    with pytest.raises(ValueError):
        _render([{**BASE, "ring_owner": ring}])


def test_ring_first_needs_the_registration_trunk():
    row = {**BASE, "source_cidr": "192.0.2.10/32", "ring_owner": {"number": "+6421824305"}}
    with pytest.raises(ValueError):
        render_routes.render([row], "bridge", "152.42.239.240", None)


def _ring_body(**limits):
    row = {**BASE, "ring_owner": {"number": "+6421824305", **limits}}
    return "\n".join(_context(_render([row])[0], "business-pukeko-construction"))


def test_ring_first_has_hard_limits_by_default():
    text = _ring_body()
    assert "ringall/${RF_HOUR})}>=12]?rf_skip" in text      # at most 12 owner rings an hour
    assert "-${RF_FROM})}>=3]?rf_skip" in text              # at most 3 per caller an hour
    assert "GROUP_COUNT(ringfirst)}>2]?rf_skip" in text     # at most 2 rings at once
    assert text.index("rf_skip)") < text.index("Dial(")      # every limit is checked BEFORE ringing


def test_the_limits_can_be_tuned():
    text = _ring_body(max_per_hour=5, max_per_caller_hour=1, max_concurrent=1)
    assert ">=5]?rf_skip" in text and ">=1]?rf_skip" in text and "GROUP_COUNT(ringfirst)}>1]?rf_skip" in text


@pytest.mark.parametrize("bad", [{"max_per_hour": 0}, {"max_per_hour": 61}, {"max_per_caller_hour": 21},
                                 {"max_concurrent": 6}, {"max_concurrent": True}, {"max_per_hour": "12"}])
def test_bad_limits_are_rejected(bad):
    with pytest.raises(ValueError):
        _ring_body(**bad)


def test_over_a_limit_the_call_still_reaches_the_assistant():
    body = _context(_render([{**BASE, "ring_owner": {"number": "+6421824305"}}])[0], "business-pukeko-construction")
    skip = next(i for i, line in enumerate(body) if line.startswith(" same => n(rf_skip)"))
    answer = next(i for i, line in enumerate(body) if "Answer()" in line)
    audio = next(i for i, line in enumerate(body) if "AudioSocket(" in line)
    assert skip < answer < audio  # the skip label falls through to Answer and the assistant


def test_registration_is_unaffected_by_ring_first():
    _, plain = _render([BASE])
    _, ringing = _render([{**BASE, "ring_owner": {"number": "+6421824305"}}])
    assert plain == ringing
