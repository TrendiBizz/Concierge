# Rust batch 12 verification

The Python reference functions generated 70 authentication, 252 enqueue, 23 route, 88 recording, 80 receipt, 20 packet, 72 inbound, 4 token-hash and 13 operational-keyword vectors. Recording output is compared by SHA-256 of the complete WAV, including clipping, random overlaps, discard/restart, odd-length input and the ten-minute limit.

Generation uses the existing local Python 3.15 environment against repository Python source with mocked database, clock and network boundaries. No real messages, Docker or Hermes runs occur. Existing version-specific SSRF vectors were preserved.

The following temporary source mutations each produced a failing test (restored immediately):

```text
device_sms: (40..=256) -> (39..=256): device_auth_matches_python FAILED as required
device_sms: !receiving_receipt -> receiving_receipt: device_auth_matches_python FAILED as required
device_sms: !sms_enabled || -> sms_enabled ||: enqueue_matches_python FAILED as required
device_sms: job.body != body -> job.body == body: enqueue_matches_python FAILED as required
device_sms: status == "sent" && receipt.is_empty() -> status == "failed" && receipt.is_empty(): receipts_match_python FAILED as required
device_sms: to != device_from || sender == device_from -> to != device_from && sender == device_from: incoming_hashes_and_operational_keywords_match_python FAILED as required
device_sms: "STOPALL" -> "STOPALL_BROKEN": incoming_hashes_and_operational_keywords_match_python FAILED as required
pbx: len > 8192 -> len > 8193: packets_match_python FAILED as required
pbx: 1024..=65535 -> 1025..=65535: routes_match_python FAILED as required
pbx: .clamp(-32768, 32767) -> .clamp(-32767, 32766): recording_matches_python FAILED as required
```

`cargo test --locked --test parity12` passes after restoring every mutation. The complete `scripts/rust-gate.sh` covers fmt, clippy with warnings denied, and tests in core-rs, hermes-gateway and social-service.

Limits: batch 12 ports decisions and framing/mixing only. Python retains database effects and running HTTP/media transports. Non-ASCII phone digits and noncanonical receipt UUID text are refused in Rust. Explicit route ports use integer JSON values.
