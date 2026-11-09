#!/usr/bin/env bash
# One-time setup for running the whole concierge on a Mac with a local LM Studio model.
# After this, everything starts by itself at every login. Safe to re-run.
#
#   scripts/setup-mac.sh          asks before installing anything
#   scripts/setup-mac.sh --yes    installs missing apps (via Homebrew) without asking
set -euo pipefail

cd "$(dirname "$0")/.."
export PATH="$HOME/.lmstudio/bin:/opt/homebrew/bin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"

ASSUME_YES=0
[ "${1:-}" = "--yes" ] && ASSUME_YES=1

say()  { printf '\n==> %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
ask()  { # ask "question" -> 0 for yes
  [ "$ASSUME_YES" = 1 ] && return 0
  local reply; read -r -p "$1 [y/N] " reply; [[ "$reply" =~ ^[Yy] ]]
}

[ "$(uname)" = "Darwin" ] || die "This script is for macOS. On Linux/VPS use: docker compose up -d --build"

# ---- 1. Docker Desktop ------------------------------------------------------------
say "Checking Docker"
if ! command -v docker >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1 && ask "Docker Desktop is not installed. Install it with Homebrew?"; then
    brew install --cask docker
  else
    die "Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and re-run this script."
  fi
fi

# ---- 2. LM Studio + its lms CLI ------------------------------------------------------
say "Checking LM Studio"
if ! command -v lms >/dev/null 2>&1; then
  if [ ! -d "/Applications/LM Studio.app" ]; then
    if command -v brew >/dev/null 2>&1 && ask "LM Studio is not installed. Install it with Homebrew?"; then
      brew install --cask lm-studio
    else
      die "Install LM Studio from https://lmstudio.ai and re-run this script."
    fi
  fi
  cat >&2 <<'MSG'

The 'lms' command-line tool is not available yet. To enable it:
  1. Open the LM Studio app once and download a model (the Discover tab). Pick one that
     supports tool calling (a recent Qwen or Llama instruct model).
  2. Make sure the CLI is installed (see https://lmstudio.ai/docs/lms; it normally lives in ~/.lmstudio/bin).
  3. Re-run scripts/setup-mac.sh
MSG
  exit 1
fi

# ---- 3. .env: secrets, xAI key, LM Studio model ---------------------------------------
say "Configuring .env"
[ -f .env ] || ./scripts/gen-env.sh

get_kv() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }
set_kv() {
  local tmp; tmp="$(mktemp)"
  K="$1" V="$2" awk 'BEGIN{FS="=";k=ENVIRON["K"];v=ENVIRON["V"];d=0}
    $1==k&&!d{print k"="v;d=1;next}{print}END{if(!d)print k"="v}' .env > "$tmp"
  cat "$tmp" > .env; rm -f "$tmp"
}

if [ -z "$(get_kv XAI_API_KEY)" ]; then
  echo "Website VOICE needs an xAI (Grok) API key. Text chat will use LM Studio either way."
  read -r -s -p "Paste your XAI_API_KEY (or press Enter to skip voice for now): " key; echo
  [ -n "$key" ] && set_kv XAI_API_KEY "$key"
  chmod 600 .env
fi

./scripts/configure-lmstudio.sh

# ---- 4. Start it, then make it automatic ------------------------------------------------
say "Starting everything (the first run builds the images and can take several minutes)"
./scripts/start-concierge.sh

say "Making it start automatically at every login"
./scripts/install-autostart-macos.sh

cat <<'MSG'

All set. From now on, everything starts by itself when you log in to your Mac.
  Dashboard:  http://127.0.0.1:8000/admin-ui   (sign in with ADMIN_TOKEN from .env)
  Stop:       ./scripts/stop-concierge.sh   (or double-click "Stop Concierge.command")
  Tip:        in Docker Desktop settings, tick "Start Docker Desktop when you sign in".
MSG
