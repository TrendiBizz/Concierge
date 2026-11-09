#!/usr/bin/env bash
# Fail-fast gate for every Rust crate CI builds with --locked. Run before every push. No pipes, so exit statuses are real
# (an earlier `cargo clippy | grep | head` hid lint failures and shipped red CI twice).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
for crate in core-rs hermes-gateway social-service; do
  cd "$ROOT/concierge-stack/$crate"
  echo "== $crate"
  cargo fmt --check
  cargo clippy --locked --all-targets -- -D warnings
  log="$(mktemp)"
  if ! cargo test --locked >"$log" 2>&1; then tail -40 "$log"; rm -f "$log"; exit 1; fi
  grep "test result" "$log" | grep -v " 0 passed" | tail -4 || true
  rm -f "$log"
done
echo GATE-ALL-OK
