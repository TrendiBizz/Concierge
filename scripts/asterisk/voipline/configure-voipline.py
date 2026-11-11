#!/usr/bin/env python3
"""Append a VoipLine registration trunk to the generated Asterisk config.

Run only after VoipLine verification, with the real SIP credentials exported.
It backs up the current generated files, adds the trunk and the tenant route,
and prints the ASTERISK_ROUTES entry to add to the bridge. It does not restart
containers or open firewall ports.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GENERATED = ROOT / "scripts/asterisk/generated"


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Set {name}")
    return value


def main() -> None:
    sip_host = required("VOIPLINE_SIP_HOST")
    sip_user = required("VOIPLINE_SIP_USER")
    sip_pass = required("VOIPLINE_SIP_PASS")
    did = required("VOIPLINE_DID")
    tenant = required("VOIPLINE_TENANT")
    port = required("VOIPLINE_BRIDGE_PORT")
    source_cidr = os.environ.get("VOIPLINE_SOURCE_CIDR", "").strip()
    if not did.startswith("+"):
        raise SystemExit("VOIPLINE_DID must be E.164, e.g. +6490000000")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", tenant):
        raise SystemExit("VOIPLINE_TENANT must be a tenant slug")
    if not re.fullmatch(r"[1-9][0-9]{3,4}", port):
        raise SystemExit("VOIPLINE_BRIDGE_PORT must be a port such as 9512")

    pjsip = GENERATED / "pjsip.conf"
    extensions = GENERATED / "extensions.conf"
    for path in (pjsip, extensions):
        if not path.exists():
            raise SystemExit(f"Missing {path}; render the base config first")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    for path in (pjsip, extensions):
        shutil.copy2(path, path.with_suffix(path.suffix + f".bak-voipline-{stamp}"))

    pjsip_block = (HERE / "pjsip.conf.block").read_text()
    pjsip_block = (pjsip_block.replace("{{SIP_HOST}}", sip_host)
                   .replace("{{SIP_USER}}", sip_user)
                   .replace("{{SIP_PASS}}", sip_pass))
    if source_cidr:
        pjsip_block += f"\n[voipline-identify]\ntype=identify\nendpoint=voipline\nmatch={source_cidr}\n"
    pjsip_text = pjsip.read_text()
    if "[voipline]" not in pjsip_text:
        pjsip_text = pjsip_text.replace("endpoint_identifier_order=ip",
                                        "endpoint_identifier_order=ip,username", 1)
        pjsip_text = pjsip_text.rstrip() + "\n\n" + pjsip_block.rstrip() + "\n"
        pjsip.write_text(pjsip_text)

    ext_block = (HERE / "extensions.conf.block").read_text()
    ext_block = ext_block.replace("{{DID}}", did).replace("{{TENANT}}", tenant).replace("{{PORT}}", port)
    ext_text = extensions.read_text()
    if "[voipline-inbound]" not in ext_text:
        ext_text = ext_text.rstrip() + "\n\n" + ext_block.rstrip() + "\n"
        extensions.write_text(ext_text)

    print("Wrote VoipLine trunk and route.")
    print("Bridge route: " + '{"tenant":"%s","number":"%s","port":%s}' % (tenant, did, port))
    print("Next: add that row to ASTERISK_ROUTES, restart the bridge and pbx, then test.")
    print("Backups: %s.bak-voipline-%s" % (pjsip, stamp))


if __name__ == "__main__":
    main()
