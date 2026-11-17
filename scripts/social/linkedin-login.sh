#!/usr/bin/env bash
# One-time login for the dedicated LinkedIn posting profile.
set -eu
PROFILE="$HOME/.trendi-linkedin-profile"
mkdir -p "$PROFILE"
open -na "Google Chrome" --args --user-data-dir="$PROFILE" https://www.linkedin.com/login
echo "Log in as Jo, open the Trendi page admin area, then close that Chrome window."
echo "Profile: $PROFILE"
