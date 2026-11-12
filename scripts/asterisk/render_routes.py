"""Render trusted SIP ingress → separate business systems.

Input is either the legacy list of rows, or an object:

    {"routes": [{"tenant","number","port","source_cidr"?}],
     "trunk":  {"server","username","password","transport"?: "udp", "port"?: 5060}}

Two ingress styles are supported and they are not interchangeable:

* ``source_cidr`` (IP authentication) — the carrier's signalling network is pinned and
  every call is demultiplexed by exact verified DID.
* ``trunk`` (SIP registration) — for a carrier that authenticates a REGISTER with a line
  number and password and delivers calls to the registered contact (Hero Internet, and
  most residential/small-business VoIP lines). The registrar's hostname is pinned as the
  only accepted source, so an unknown IP is still rejected.

Never infer a business from caller ID, and never let the caller/model choose a tenant.
"""
import ipaddress
import json
from pathlib import Path
import re
import sys


HOST = re.compile(r'[a-zA-Z0-9.-]+')


def _trunk(value):
    if not isinstance(value, dict):
        raise ValueError('Trunk configuration must be an object')
    server = str(value.get('server') or '')
    username = str(value.get('username') or '')
    password = str(value.get('password') or '')
    transport = str(value.get('transport') or 'udp').lower()
    port = value.get('port', 5060)
    if not HOST.fullmatch(server) or not server:
        raise ValueError('Invalid trunk server')
    if not re.fullmatch(r'[0-9+]{4,20}', username):
        raise ValueError('Invalid trunk username')
    if not isinstance(password, str) or len(password) < 8 or re.search(r'[\s;\[\]]', password):
        raise ValueError('Trunk password must be at least eight characters with no whitespace or separators')
    if transport != 'udp':
        raise ValueError('Only udp registration is supported; TLS needs certificates that this renderer does not place')
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError('Invalid trunk port')
    return {'server': server, 'username': username, 'password': password,
            'transport': transport, 'port': port}


def render(rows, bridge_host, public_ip=None, trunk=None):
    if not HOST.fullmatch(bridge_host):
        raise ValueError('Invalid private bridge hostname')
    trunk = _trunk(trunk) if trunk else None
    contexts = ['[general]', 'static=yes', 'writeprotect=yes', '[default]', 'exten => _.,1,Hangup(21)']
    pjsip = ['[global]', 'type=global', 'endpoint_identifier_order=ip',
             '[transport-udp]', 'type=transport', 'protocol=udp', 'bind=0.0.0.0:5060']
    if public_ip:
        # Advertise the host's public address in SDP/Via, and treat the private
        # container network as local; without this the carrier would be told to send
        # media to 172.30.91.2 and hear nothing.
        pjsip += ['external_media_address=' + public_ip,
                  'external_signaling_address=' + public_ip,
                  'local_net=172.30.91.0/29']
    ports = set()
    numbers = set()
    slugs = set()
    groups = {}
    for row in rows:
        slug, number, port = row['tenant'], row['number'], row['port']
        source = row.get('source_cidr')
        if source is None and trunk is None:
            raise ValueError('Each route needs source_cidr, or supply a registration trunk')
        if source is not None:
            source = ipaddress.ip_network(source, strict=True)
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', slug) or slug in slugs:
            raise ValueError('Unique valid business slug required')
        if not re.fullmatch(r'\+[1-9]\d{6,14}', number) or number in numbers:
            raise ValueError('Unique valid ingress number required')
        if not isinstance(port, int) or not 1024 <= port <= 65535 or port in ports:
            raise ValueError('Unique private bridge port required')
        if source is not None:
            if source.prefixlen == 0 or any(source != s and source.overlaps(s)
                                            for s in groups
                                            if s is not None and source.version == s.version):
                raise ValueError('Use unambiguous verified provider source networks')
        ports.add(port)
        numbers.add(number)
        slugs.add(slug)
        groups.setdefault(source, []).append(row)
        contexts += [f'[business-{slug}]', 'exten => s,1,Answer()', ' same => n,Set(TIMEOUT(absolute)=600)',
                     ' same => n,Set(CONCIERGE_CALL=${FILTER(0-9a-f-,${SHELL(cat /proc/sys/kernel/random/uuid)})})',
                     f' same => n,AudioSocket(${{CONCIERGE_CALL}},{bridge_host}:{port})', ' same => n,Hangup()']
    if not rows:
        raise ValueError('No business routes')
    if trunk:
        # One registration carries the account; every number on it is routed by exact DID
        # in the ingress context below, exactly like the IP-authenticated case.
        pjsip += ['[concierge-reg]', 'type=registration',
                  f"server_uri=sip:{trunk['server']}:{trunk['port']}",
                  f"client_uri=sip:{trunk['username']}@{trunk['server']}",
                  'outbound_auth=concierge-reg-auth', 'retry_interval=60',
                  f"contact_user={trunk['username']}",
                  '[concierge-reg-auth]', 'type=auth', 'auth_type=userpass',
                  f"username={trunk['username']}", f"password={trunk['password']}",
                  '[concierge-reg-aor]', 'type=aor',
                  f"contact=sip:{trunk['server']}:{trunk['port']}",
                  '[concierge-reg]', 'type=endpoint', 'context=concierge-ingress-1',
                  'disallow=all', 'allow=ulaw,alaw', 'direct_media=no', 'rtp_symmetric=yes',
                  'force_rport=yes', 'rewrite_contact=yes', 'outbound_auth=concierge-reg-auth',
                  f"from_user={trunk['username']}", 'aors=concierge-reg-aor',
                  '[concierge-reg]', 'type=identify', 'endpoint=concierge-reg',
                  f"match={trunk['server']}"]
        ingress = [(row['number'], row['tenant']) for row in rows]
        contexts.append('[concierge-ingress-1]')
        contexts += [f"exten => {number},1,Goto(business-{slug},s,1)" for number, slug in ingress]
        if len(rows) == 1:
            # A registration trunk authenticates one account to one line. Providers vary in
            # whether the dialled number arrives as +64…, 0…, or 64…, so a single-line account
            # accepts any DNIS on its own authenticated trunk. With more than one route the
            # exact DID entries above are the only mapping and anything else is rejected.
            contexts.append(f"exten => _.,1,Goto(business-{rows[0]['tenant']},s,1)")
        else:
            contexts.append('exten => _.,1,Hangup(21)')
    for i, (source, businesses) in enumerate(
            (item for item in groups.items() if item[0] is not None)):
        trunk_name = f'concierge-ingress-{i + (2 if trunk else 1)}'
        contexts.append(f'[{trunk_name}]')
        for row in businesses:
            contexts.append(f"exten => {row['number']},1,Goto(business-{row['tenant']},s,1)")
        contexts.append('exten => _.,1,Hangup(21)')
        pjsip += [f'[{trunk_name}]', 'type=endpoint', f'context={trunk_name}', 'disallow=all',
                  'allow=ulaw,alaw', 'direct_media=no', 'rtp_symmetric=yes', 'force_rport=yes',
                  'rewrite_contact=yes',
                  f'[{trunk_name}-identify]', 'type=identify', f'endpoint={trunk_name}',
                  f'match={source}']
    return '\n'.join(contexts) + '\n', '\n'.join(pjsip) + '\n'


def load(path):
    """Accept the legacy bare list or the documented object form."""
    value = json.loads(Path(path).read_text())
    if isinstance(value, list):
        return value, None
    if not isinstance(value, dict):
        raise ValueError('Routes file must be a list or an object')
    rows, trunk = value.get('routes'), value.get('trunk')
    if not isinstance(rows, list):
        raise ValueError('routes must be a list')
    return rows, trunk


if __name__ == '__main__':
    rows, trunk = load(sys.argv[1])
    extensions, pjsip = render(rows, sys.argv[3] if len(sys.argv) > 3 else 'bridge',
                               sys.argv[4] if len(sys.argv) > 4 else None, trunk)
    target = Path(sys.argv[2])
    target.mkdir(parents=True, exist_ok=True)
    (target / 'extensions.conf').write_text(extensions)
    (target / 'pjsip.conf').write_text(pjsip)
    # Restrict media to a small published range instead of the 10000-20000
    # default, so the public firewall/port mapping stays tight.
    (target / 'rtp.conf').write_text('[general]\nrtpstart=10000\nrtpend=10099\n')
