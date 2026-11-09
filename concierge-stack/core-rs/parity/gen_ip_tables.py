"""Dump CPython's ipaddress special-purpose tables so the Rust SSRF guard cannot drift by retyping.
These tables change between Python patch releases, so regenerate with the interpreter that runs production:

    python3 concierge-stack/core-rs/parity/gen_ip_tables.py > concierge-stack/core-rs/src/ip_tables.json
"""
import ipaddress
import json
import sys

c4, c6 = ipaddress._IPv4Constants, ipaddress._IPv6Constants
print(json.dumps({
    "python": sys.version.split()[0],
    "v4_private": [str(n) for n in c4._private_networks], "v4_exceptions": [str(n) for n in c4._private_networks_exceptions],
    "v4_public": str(c4._public_network),
    "v6_private": [str(n) for n in c6._private_networks], "v6_exceptions": [str(n) for n in c6._private_networks_exceptions],
}, indent=1))
