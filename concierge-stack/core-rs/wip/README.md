# Unverified work in progress (NOT compiled, NOT part of the crate)

`pbx.rs.txt` (Asterisk route validation, AudioSocket framing, call-recording mixer with byte-exact WAV output) and
`device_sms.rs.txt` (paired-phone SMS authentication, send validation, job/receipt/inbound decisions) were written and compile,
but have **no golden vectors and no parity tests yet**. Do not treat them as ported. To finish: move each to `src/`, add the `mod`
lines to `src/lib.rs`, write `parity/gen_vectors12.py` (drive the real `device_sms.device_auth`/`enqueue` and
`TelephoneRecording` with a fake database and clock) and `tests/parity12.rs`, and run `scripts/rust-gate.sh`.
