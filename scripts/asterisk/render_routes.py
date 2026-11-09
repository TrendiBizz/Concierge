"""Render trusted SIP source + exact destination → separate business systems.

Input JSON rows: tenant, number, port, source_cidr. Never infers a business from
caller ID. Shared provider trunks are demultiplexed by exact verified DID.
"""
import ipaddress
import json
from pathlib import Path
import re
import sys


def render(rows, bridge_host):
    if not re.fullmatch(r'[a-zA-Z0-9.-]+', bridge_host):
        raise ValueError('Invalid private bridge hostname')
    contexts=['[general]', 'static=yes', 'writeprotect=yes', '[default]', 'exten => _.,1,Hangup(21)']
    pjsip=['[global]', 'type=global', 'endpoint_identifier_order=ip', '[transport-udp]', 'type=transport', 'protocol=udp', 'bind=0.0.0.0:5060']
    ports=set();numbers=set();slugs=set();groups={}
    for row in rows:
        slug,number,port=row['tenant'],row['number'],row['port']
        source=ipaddress.ip_network(row['source_cidr'],strict=True)
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}',slug) or slug in slugs:
            raise ValueError('Unique valid business slug required')
        if not re.fullmatch(r'\+[1-9]\d{6,14}',number) or number in numbers:
            raise ValueError('Unique valid ingress number required')
        if not isinstance(port,int) or not 1024<=port<=65535 or port in ports:
            raise ValueError('Unique private bridge port required')
        if source.prefixlen==0 or any(source!=s and source.overlaps(s) for s in groups if source.version==s.version):
            raise ValueError('Use unambiguous verified provider source networks')
        ports.add(port);numbers.add(number);slugs.add(slug)
        groups.setdefault(source,[]).append(row)
        contexts += [f'[business-{slug}]',f'exten => s,1,Answer()', ' same => n,Set(TIMEOUT(absolute)=600)',
                     ' same => n,Set(CONCIERGE_CALL=${FILTER(0-9a-f-,${SHELL(cat /proc/sys/kernel/random/uuid)})})',
                     f' same => n,AudioSocket(${{CONCIERGE_CALL}},{bridge_host}:{port})', ' same => n,Hangup()']
    if not rows:
        raise ValueError('No business routes')
    for i,(source,businesses) in enumerate(groups.items()):
        trunk=f'concierge-ingress-{i+1}'
        contexts.append(f'[{trunk}]')
        for row in businesses:
            contexts.append(f"exten => {row['number']},1,Goto(business-{row['tenant']},s,1)")
        contexts.append('exten => _.,1,Hangup(21)')
        pjsip += [f'[{trunk}]','type=endpoint',f'context={trunk}','disallow=all','allow=ulaw,alaw','direct_media=no',
                  f'[{trunk}-identify]','type=identify',f'endpoint={trunk}',f'match={source}']
    return '\n'.join(contexts)+'\n','\n'.join(pjsip)+'\n'


if __name__=='__main__':
    rows=json.loads(Path(sys.argv[1]).read_text())
    extensions,pjsip=render(rows,sys.argv[3] if len(sys.argv)>3 else 'bridge')
    target=Path(sys.argv[2]);target.mkdir(parents=True,exist_ok=True)
    (target/'extensions.conf').write_text(extensions)
    (target/'pjsip.conf').write_text(pjsip)
