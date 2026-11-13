# A live Stripe secret key was sitting in a transcript; nothing would have stopped it reaching git

Found while reading a background grep's output: a real Stripe **live** secret key
(`sk_live_…`) and the matching live publishable key were in plaintext inside a DeepSeek Harness
conversation log on this Mac.

## What was and was not exposed

| Location | Contained a live credential? |
|---|---|
| The repository (tracked files, `origin/main`) | **No** |
| `concierge-integration/QA/verification/ASTERISK_GROK_VERIFICATION_2026-11-09.md` | **No** — the match was the filename `asterisk_live_..._integration.py`. A substring match, not a credential. |
| `~/.dsh/storages/session_projcache/sessions/session-44c2e840-….json` | **Yes** — one `sk_live_` secret, redacted on 14 Nov |

The first alarm I raised was wrong and worth recording as such: `sk_live_` appears inside
`asteri**sk_live_**…`, so any naive scan produces a false positive on that filename.

## Fixed

1. **Redacted in place.** The transcript's one live secret was replaced with `sk_live_[REDACTED]`
   (one substitution, file still valid JSON, 46,351 → 46,320 bytes). A follow-up scan of `~/.dsh`,
   `~/Documents` and `~/work-staging` finds **no** live secret or webhook secret anywhere.
2. **The repository now refuses them.** `api/tests/test_no_live_secrets_committed.py` reads every
   tracked text file and fails on live Stripe secret/restricted/webhook keys, GitHub tokens and AWS
   access keys. The pattern uses `(?<![A-Za-z0-9])` so `asterisk_live_...` is not reported, and the
   deterministic Rust parity fixtures (`whsec_AAECAwQFBgcI…` = bytes 00 01 02 03) are allowlisted by
   explicit path.

## Proof the guard bites

| Run | Result |
|---|---|
| No probe | **3 passed** |
| A staged `scripts/vps/leak_probe.sh` containing `sk_live_…` | **fails**: `scripts/vps/leak_probe.sh: stripe secret` |
| Probe removed | **3 passed** |
| Full suite | **1141 passed** |

Untracked files are deliberately not scanned — the guard runs on what git would actually commit.

## Still open, for the operator

* **Rotate that live Stripe secret key** in the dashboard. It was typed into a chat, so it existed
  in a transcript, may exist in any backup of this machine, and cannot be assumed private. Nothing
  in the Concierge product uses it (the platform billing path uses a webhook *signing* secret, not
  this key), so rotation should be harmless — but only you can do it.
* The harness itself writes conversation logs to disk in cleartext. Masking credentials in
  transcripts is an upstream change, not something this repository can enforce.
