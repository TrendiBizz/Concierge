"""SIP ingress renderer: IP authentication and registration trunks.

The renderer is the only place a carrier's identity becomes a Concierge business, so these
tests pin the two promises that matter: an unknown source can never reach a business, and the
line password goes into pjsip.conf only.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'render_routes', ROOT / 'scripts' / 'asterisk' / 'render_routes.py')
routes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(routes)

TRUNK = {'server': 'sip.example.test', 'username': '092431347',
         'password': 'CorrectHorse9Battery', 'transport': 'udp', 'port': 5060}
ROW = {'tenant': 'pukeko-construction', 'number': '+6492431347', 'port': 9510}


def test_ip_authenticated_list_still_renders_the_same_way():
    rows = [{'tenant': 'biz', 'number': '+6495550100', 'port': 9101,
             'source_cidr': '192.0.2.10/32'}]
    extensions, pjsip = routes.render(rows, 'bridge', '152.42.239.240')
    assert '[concierge-ingress-1]' in extensions
    assert 'exten => +6495550100,1,Goto(business-biz,s,1)' in extensions
    assert 'type=identify' in pjsip and 'match=192.0.2.10/32' in pjsip
    assert 'concierge-reg' not in pjsip


def test_registration_trunk_renders_auth_and_pins_the_registrar():
    extensions, pjsip = routes.render([ROW], 'bridge', '152.42.239.240', TRUNK)
    assert 'type=registration' in pjsip
    assert 'server_uri=sip:sip.example.test:5060' in pjsip
    assert 'client_uri=sip:092431347@sip.example.test' in pjsip
    assert 'type=auth' in pjsip and 'type=aor' in pjsip
    assert 'match=sip.example.test' in pjsip          # only the registrar may send calls
    assert 'external_signaling_address=152.42.239.240' in pjsip
    assert 'exten => +6492431347,1,Goto(business-pukeko-construction,s,1)' in extensions


def test_registration_password_is_confined_to_pjsip():
    extensions, pjsip = routes.render([ROW], 'bridge', None, TRUNK)
    assert TRUNK['password'] in pjsip
    assert TRUNK['password'] not in extensions


def test_route_without_source_or_trunk_is_refused():
    with pytest.raises(ValueError):
        routes.render([ROW], 'bridge')


def test_trunk_rejects_weak_or_ambiguous_credentials():
    with pytest.raises(ValueError):
        routes.render([ROW], 'bridge', None, {**TRUNK, 'password': 'short'})
    with pytest.raises(ValueError):
        routes.render([ROW], 'bridge', None, {**TRUNK, 'password': 'space in password'})
    with pytest.raises(ValueError):
        routes.render([ROW], 'bridge', None, {**TRUNK, 'server': 'sip.example.test;evil'})
    with pytest.raises(ValueError):
        routes.render([ROW], 'bridge', None, {**TRUNK, 'transport': 'tls'})


def test_registration_and_ip_trunks_do_not_share_a_context_name():
    rows = [ROW, {'tenant': 'other', 'number': '+6495550100', 'port': 9101,
                  'source_cidr': '192.0.2.10/32'}]
    extensions, pjsip = routes.render(rows, 'bridge', None, TRUNK)
    assert '[concierge-ingress-1]' in extensions      # registration lives here
    assert '[concierge-ingress-2]' in extensions      # IP trunk moved out of the way
    for number, slug in (('+6492431347', 'pukeko-construction'), ('+6495550100', 'other')):
        assert f'exten => {number},1,Goto(business-{slug},s,1)' in extensions


def test_duplicate_numbers_and_ports_are_refused():
    rows = [ROW, dict(ROW, tenant='second')]
    with pytest.raises(ValueError):
        routes.render(rows, 'bridge', None, TRUNK)


def test_loader_accepts_legacy_list_and_object_form(tmp_path):
    legacy = tmp_path / 'legacy.json'
    legacy.write_text('[{"tenant":"b","number":"+6495550100","port":9101,'
                      '"source_cidr":"192.0.2.10/32"}]')
    rows, trunk = routes.load(legacy)
    assert isinstance(rows, list) and trunk is None
    modern = tmp_path / 'modern.json'
    modern.write_text('{"routes":[{"tenant":"b","number":"+6495550100","port":9101}],'
                      '"trunk":{"server":"sip.example.test","username":"092431347",'
                      '"password":"CorrectHorse9Battery"}}')
    rows, trunk = routes.load(modern)
    assert rows and trunk['server'] == 'sip.example.test'


def test_a_single_line_trunk_accepts_any_dnis_but_a_multi_line_one_does_not():
    single_ext, _ = routes.render([ROW], 'bridge', None, TRUNK)
    assert f"exten => _.,1,Goto(business-{ROW['tenant']},s,1)" in single_ext
    two = [ROW, {'tenant': 'other', 'number': '+6495550100', 'port': 9101}]
    two_ext, _ = routes.render(two, 'bridge', None, TRUNK)
    assert "exten => _.,1,Hangup(21)" in two_ext
    assert "exten => _.,1,Goto(business-other" not in two_ext


def test_the_trunk_route_carries_a_take_over_context_and_a_fallback():
    import runpy
    from pathlib import Path
    renderer = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/asterisk/render_routes.py'))
    trunk = {'server': 'sip.hero.co.nz', 'username': '092431347', 'password': 'longenoughpass'}
    extensions, _ = renderer['render'](
        [{'tenant': 'alpha', 'number': '+6495550100', 'port': 9101}], 'bridge', None, trunk)
    lines = extensions.splitlines()
    assert '[business-alpha-takeover]' in lines
    assert ' same => n,Dial(PJSIP/${CONCIERGE_TRANSFER}@concierge-reg,30,r)' in lines
    # Nobody answered: the caller goes back to the assistant instead of being dropped.
    assert ' same => n(ai),Goto(business-alpha,s,1)' in lines
    assert ' same => n(done),Hangup()' in lines
    # The redirect target is sanitised before it is used in a dial string.
    assert 'exten => s,1,Set(CONCIERGE_TRANSFER=${FILTER(0-9,${CONCIERGE_TRANSFER})})' in lines


def test_manager_config_is_scoped_and_refuses_weak_secrets():
    import runpy
    from pathlib import Path
    renderer = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/asterisk/render_routes.py'))
    manager = renderer['render_manager']('a' * 40)
    assert 'enabled = yes' in manager
    assert 'read = call,reporting' in manager
    assert 'write = call,originate' in manager
    assert 'webenabled = no' in manager
    assert 'command' not in manager.split('[concierge]')[1]
    for bad in ('short', 'has space in it ' * 3, 'x' * 23):
        with __import__('pytest').raises(ValueError):
            renderer['render_manager'](bad)
