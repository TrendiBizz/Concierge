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


def test_registration_is_unaffected_by_ring_first():
    _, plain = _render([BASE])
    _, ringing = _render([{**BASE, "ring_owner": {"number": "+6421824305"}}])
    assert plain == ringing
