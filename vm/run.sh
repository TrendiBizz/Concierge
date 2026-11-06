#!/usr/bin/env bash
# Concierge VM test bundle launcher.
#
#   ./run.sh                 prepare (.env, site) and start everything
#   ./run.sh prepare         prepare only
#   ./run.sh down            stop (keeps data)
#   ./run.sh reset           stop AND delete this bundle's Twenty data (asks first)
#
# Optional environment:
#   SITE_ZIP=/path/concierge-site.zip   where to unzip the site from
#                                        (default: ./concierge-site.zip, then ~/Downloads/concierge-site.zip)
#   TWENTY_API_KEY=...                  Twenty API key for the bridge (never stored in a file here)
#   TWENTY_PORT BRIDGE_PORT SITE_PORT   change host ports (the site expects 3010 / 4410 by default)
set -euo pipefail
cd "$(dirname "$0")"

cmd="${1:-up}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1" >&2; exit 1; }; }
need docker
docker compose version >/dev/null 2>&1 || { echo "Missing: docker compose plugin" >&2; exit 1; }

rand() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$1"; }

prepare() {
  # 1) secrets for the database and Twenty, generated once, kept out of git
  if [ ! -f .env ]; then
    umask 077
    {
      echo "PG_PASSWORD=$(rand 24)"
      echo "APP_SECRET=$(rand 48)"
    } > .env
    echo "Created .env with new random secrets."
  fi

  # 2) the website, unzipped into ./site
  if [ ! -f site/index.html ]; then
    zip="${SITE_ZIP:-}"
    if [ -z "$zip" ]; then
      for c in ./concierge-site.zip "$HOME/Downloads/concierge-site.zip"; do
        [ -f "$c" ] && { zip="$c"; break; }
      done
    fi
    [ -n "$zip" ] && [ -f "$zip" ] || { echo "Site zip not found. Set SITE_ZIP=/path/to/concierge-site.zip" >&2; exit 1; }
    need unzip
    tmp="$(mktemp -d)"
    unzip -q "$zip" -d "$tmp"
    # the zip may hold the pages at the top level or inside one folder
    src="$tmp"
    [ -f "$tmp/index.html" ] || src="$(dirname "$(find "$tmp" -name index.html -not -path '*/__MACOSX/*' | head -n1)")"
    [ -f "$src/index.html" ] || { echo "No index.html found in $zip" >&2; exit 1; }
    mkdir -p site
    cp -R "$src"/. site/
    rm -rf "$tmp"
    echo "Site unzipped from $zip ($(find site -name '*.html' | wc -l | tr -d ' ') pages)."
  fi
}

case "$cmd" in
  prepare) prepare ;;
  up)
    prepare
    docker compose up -d
    echo
    echo "Site:    http://localhost:${SITE_PORT:-8080}/"
    echo "CRM:     http://localhost:${TWENTY_PORT:-3010}/   (first run: create a workspace, then an API key)"
    echo "Bridge:  http://localhost:${BRIDGE_PORT:-4410}/lead"
    if [ -z "${TWENTY_API_KEY:-}" ]; then
      echo
      echo "No TWENTY_API_KEY set: the bridge answers 503 and the contact form falls back to email."
      echo "After creating a Twenty API key:  TWENTY_API_KEY=<key> ./run.sh   (or: docker compose up -d bridge)"
    fi
    ;;
  down) docker compose down ;;
  reset)
    read -r -p "Delete this bundle's Twenty database and files? Type yes: " a
    [ "$a" = "yes" ] && docker compose down -v || echo "Cancelled."
    ;;
  *) echo "Usage: $0 [up|prepare|down|reset]" >&2; exit 2 ;;
esac
