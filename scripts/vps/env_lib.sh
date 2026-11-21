#!/usr/bin/env bash
# Read an env file as data, never as shell.
#
# Why this exists (2026-11-15): the scripts used `. /opt/trendi/shared/api.env`, and the file is
# also consumed by compose as plain KEY=VALUE data. Compose does not run a shell, so a
# value may legally contain anything — and ours does:
#
#     ASTERISK_CHANNEL_DIAL=PJSIP/<number>@concierge
#
# Sourcing that line is a redirect: bash printed "number: No such file or directory" and left
# ASTERISK_CHANNEL_DIAL as the truncated string "PJSIP/". check-inbound-chain.sh printed the
# error on every cron run and only worked because it happened to need ADMIN_TOKEN, which is
# harmless; any script that needed the dial string would have placed a broken call.
#
# Usage:  . "$(dirname "$0")/env_lib.sh";  load_env /opt/trendi/shared/api.env
# Missing file: returns 1 and exports nothing. Never exits the caller's shell.

load_env() {
  local file="${1:-/opt/trendi/shared/api.env}" line key value
  [ -r "$file" ] || return 1
  while IFS= read -r line || [ -n "$line" ]; do
    line=${line%$'\r'}
    case $line in ''|'#'*) continue ;; esac
    case $line in *=*) ;; *) continue ;; esac
    key=${line%%=*}
    value=${line#*=}
    [[ $key =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    # Strip one matching pair of surrounding quotes, the way compose does; never otherwise.
    case $value in
      \"*\") value=${value#\"}; value=${value%\"} ;;
      \'*\') value=${value#\'}; value=${value%\'} ;;
    esac
    export "$key=$value"
  done < "$file"
  return 0
}
