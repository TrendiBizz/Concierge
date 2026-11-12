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


def _ring_owner(row, trunk):
    """Optional per-route ``ring_owner``: ring the owner's own phone first.

    Anything other than an answered call (declined, busy, unreachable, no answer) falls straight
    through to the assistant, so the caller is never left waiting. Needs the registration trunk
    because the outbound leg goes out over it.
    """
    value = row.get('ring_owner')
    if not value:
        return None
    if trunk is None:
        raise ValueError('Ring-first needs the registration trunk to place the outbound call')
    if not isinstance(value, dict):
        raise ValueError('ring_owner must be an object')
    number = str(value.get('number') or '')
    seconds = value.get('seconds', 15)
    if not re.fullmatch(r'\+[1-9]\d{6,14}', number):
        raise ValueError('ring_owner.number must be an international number such as +6421...')
    if not isinstance(seconds, int) or isinstance(seconds, bool) or not 5 <= seconds <= 45:
        raise ValueError('ring_owner.seconds must be between 5 and 45')
    limits = {}
    for key, default, low, high in (('max_per_hour', 12, 1, 60), ('max_per_caller_hour', 3, 1, 20),
                                    ('max_concurrent', 2, 1, 5)):
        found = value.get(key, default)
        if not isinstance(found, int) or isinstance(found, bool) or not low <= found <= high:
            raise ValueError(f'ring_owner.{key} must be between {low} and {high}')
        limits[key] = found
    return {'digits': number[1:], 'seconds': seconds, **limits}


def _ring_lines(slug, ring):
    """Dialplan that rings the owner first, with hard limits so nobody can use it to flood a phone.

    A call is only rung through while: fewer than max_per_hour owner rings were placed this hour,
    this caller has had fewer than max_per_caller_hour this hour, and fewer than max_concurrent
    rings are in progress. Anything over a limit goes straight to the assistant. The counters live in
    AstDB, keyed by the hour, so they need no cleanup to stay correct.
    """
    return [
        'exten => s,1,NoOp(Ring owner first for ' + slug + ')',
        ' same => n,Set(RF_HOUR=${STRFTIME(${EPOCH},,%Y%m%d%H)})',
        ' same => n,Set(RF_FROM=${FILTER(0-9,${CALLERID(num)})})',
        ' same => n,GotoIf($["${DB_EXISTS(ringall/${RF_HOUR})}"="1"]?rf_a)',
        ' same => n,Set(DB(ringall/${RF_HOUR})=0)',
        ' same => n(rf_a),GotoIf($[${DB(ringall/${RF_HOUR})}>=' + str(ring['max_per_hour']) + ']?rf_skip)',
        ' same => n,GotoIf($["${DB_EXISTS(ringfrom/${RF_HOUR}-${RF_FROM})}"="1"]?rf_b)',
        ' same => n,Set(DB(ringfrom/${RF_HOUR}-${RF_FROM})=0)',
        ' same => n(rf_b),GotoIf($[${DB(ringfrom/${RF_HOUR}-${RF_FROM})}>=' + str(ring['max_per_caller_hour']) + ']?rf_skip)',
        ' same => n,Set(GROUP()=ringfirst)',
        ' same => n,GotoIf($[${GROUP_COUNT(ringfirst)}>' + str(ring['max_concurrent']) + ']?rf_skip)',
        ' same => n,Set(DB(ringall/${RF_HOUR})=$[${DB(ringall/${RF_HOUR})}+1])',
        ' same => n,Set(DB(ringfrom/${RF_HOUR}-${RF_FROM})=$[${DB(ringfrom/${RF_HOUR}-${RF_FROM})}+1])',
        ' same => n,Dial(PJSIP/' + ring['digits'] + '@concierge-reg,' + str(ring['seconds']) + ',r)',
        ' same => n,GotoIf($["${DIALSTATUS}"="ANSWER"]?done)',
        ' same => n,GotoIf($["${DIALSTATUS}"="CANCEL"]?done)',
        ' same => n(rf_skip),Set(GROUP()=aicall)',
        ' same => n,Answer()',
    ]


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
        ring = _ring_owner(row, trunk)
        if ring:
            start = _ring_lines(slug, ring)
            end = [' same => n,Hangup()', ' same => n(done),Hangup()']
        else:
            start = ['exten => s,1,Answer()']
            end = [' same => n,Hangup()']
        contexts += ([f'[business-{slug}]'] + start +
                     [' same => n,Set(TIMEOUT(absolute)=600)',
                      ' same => n,Set(CONCIERGE_CALL=${FILTER(0-9a-f-,${SHELL(cat /proc/sys/kernel/random/uuid)})})',
                      f' same => n,AudioSocket(${{CONCIERGE_CALL}},{bridge_host}:{port})'] + end)
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
        # One control context per business. The API redirects a live caller channel here
        # after writing CONCIERGE_TRANSFER (AMI Setvar): ring the human through the same
        # trunk, bridge them, and fall back to the assistant if nobody answers. Dropping a
        # caller into silence because the owner missed the ring is not acceptable.
        for row in rows:
            slug = row['tenant']
            contexts += [
                f'[business-{slug}-takeover]',
                'exten => s,1,Set(CONCIERGE_TRANSFER=${FILTER(0-9,${CONCIERGE_TRANSFER})})',
                f' same => n,NoOp(Take-over for {slug} from ${{CALLERID(num)}} to ${{CONCIERGE_TRANSFER}})',
                ' same => n,GotoIf($["${CONCIERGE_TRANSFER}"=""]?ai)',
                ' same => n,Dial(PJSIP/${CONCIERGE_TRANSFER}@concierge-reg,30,r)',
                ' same => n,GotoIf($["${DIALSTATUS}"="ANSWER"]?done:ai)',
                f' same => n(ai),Goto(business-{slug},s,1)',
                ' same => n(done),Hangup()']
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


def render_manager(secret, user='concierge', port=5038):
    """Render ``manager.conf`` for the private AMI listener.

    The listener is never published to the host: the PBX and the API share a private Docker
    network. The AMI user gets exactly the classes call control needs and nothing else, so a
    leaked secret cannot run CLI commands or touch configuration.
    """
    if not re.fullmatch(r'[A-Za-z0-9_]{1,32}', str(user or '')):
        raise ValueError('Invalid AMI user name')
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError('Invalid AMI port')
    if not isinstance(secret, str) or len(secret) < 24 or re.search(r'[^\x21-\x7e]', secret):
        raise ValueError('AMI secret must be at least 24 printable characters')
    return ('[general]\n'
            'enabled = yes\n'
            f'port = {port}\n'
            'bindaddr = 0.0.0.0\n'
            'displayconnects = no\n'
            'webenabled = no\n'
            f'[{user}]\n'
            f'secret = {secret}\n'
            'read = call,reporting\n'
            'write = call,originate\n')


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
    args = list(sys.argv[1:])
    manager_secret = None
    if '--manager-secret-file' in args:
        index = args.index('--manager-secret-file')
        manager_secret = Path(args[index + 1]).read_text().strip()
        del args[index:index + 2]
    rows, trunk = load(args[0])
    extensions, pjsip = render(rows, args[2] if len(args) > 2 else 'bridge',
                               args[3] if len(args) > 3 else None, trunk)
    target = Path(args[1])
    target.mkdir(parents=True, exist_ok=True)
    (target / 'extensions.conf').write_text(extensions)
    (target / 'pjsip.conf').write_text(pjsip)
    # Restrict media to a small published range instead of the 10000-20000
    # default, so the public firewall/port mapping stays tight.
    (target / 'rtp.conf').write_text('[general]\nrtpstart=10000\nrtpend=10099\n')
    if manager_secret:
        manager = target / 'manager.conf'
        manager.write_text(render_manager(manager_secret))
        manager.chmod(0o600)
