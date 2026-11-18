# Booking / quote-guard review fixes — 2026-11-19

Source: post-merge review of PR #1 (merged 2026-11-04, `010db79`), reading `booking.py` and `guard.py` only.

| # | Cause | Fix | Test |
|---|---|---|---|
| 1 | `guard.AMOUNT_RE` matched only `$<digits>`; "500 dollars", "NZD 500", "NZ$500", "$5k" passed the quote-guard unchecked | regex also matches currency words/codes and a `k` suffix | `test_units.py::test_guard_catches_written_and_abbreviated_prices` |
| 2 | read-back key included `consent`; a confirm that omitted `consent_to_contact` never matched, so the visitor was asked to confirm again | `consent` removed from the key | `test_booking_confirm_consistency.py::test_confirm_matches_even_if_consent_flag_differs` |
| 3 | duplicate-confirm check ran before the advisory lock; a racing confirm got "just taken" instead of the existing booking | `_earlier_booking()` re-checked inside the lock when the slot is gone | `...::test_racing_duplicate_confirm_returns_the_existing_booking` |

Mutation check: each fix reverted in turn, the matching test went red, fix restored (55 passed).
Not done: full suite shows 33 failures from Postgres refusing connections on 127.0.0.1:55433 in this session; the 55 tests above do not need it. Not deployed.
