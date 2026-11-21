# VoipLine Telecom SIP trunk

Preparation only. Do not apply until VoipLine verification completes and a NZ
number + SIP Line are active.

## What VoipLine must provide
- NZ number (DID)
- SIP domain/proxy
- SIP username/auth ID and password
- Any signalling source IPs (for a tight firewall/identify match)
- Whether registration or IP authentication is required

## Apply
1. Export the values from `.env.example` in the shell.
2. Render/confirm the base config:
   `python3 scripts/asterisk/render_routes.py <routes.json> scripts/asterisk/generated`
3. Append the trunk and tenant route:
   `python3 scripts/asterisk/voipline/configure-voipline.py`
4. Add the printed bridge row to `ASTERISK_ROUTES` in the private Asterisk env.
5. Start with the VoipLine override (`scripts/asterisk/voipline/compose.voipline.yml`) through a script in `scripts/asterisk/`.
6. Firewall: allow UDP 5060 and 10000-10099 from VoipLine's signalling IPs only.
7. Reload and verify: `scripts/asterisk/cutover_to_tenant.sh` reloads the PBX and checks the registrations.
8. Test: dial the NZ number, confirm the AI answers, the CRM enquiry is created,
   and the call finishes with a transcript.

## Notes
- The base `phone` network is internal; the override adds an egress network.
- The PBX already advertises the VPS public IP in SDP/Via. Keep RTP within
  10000-10099.
- Registration is used because VoipLine supports "Create SIP registration".
  If VoipLine supplies fixed source IPs, also set `VOIPLINE_SOURCE_CIDR` so
  inbound requests are identified by IP as well as username.
- Do not expose AudioSocket, ARI or the database.
