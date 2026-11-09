#!/bin/bash
# Start the preserved Grok Voice agent with its existing message/SMS configuration.
set -euo pipefail
cd "$(dirname "$0")"
exec ./concierge-stack/run-local.sh
