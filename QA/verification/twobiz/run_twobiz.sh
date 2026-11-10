#!/bin/sh
# Override DATABASE_URL BEFORE Python starts, so the lru_cache in config.get_settings() is filled
# with the throwaway database rather than production. This is the fix for the earlier incident:
# mutating os.environ after the cache is warm had no effect.
set -e
BASE="$(python -c 'from app.config import get_settings; print(get_settings().database_url)')"
VERIFY="$(echo "$BASE" | sed 's#/[^/]*$#/concierge_twobiz_verify#')"
echo "target: $(echo "$VERIFY" | sed 's#://[^@]*@#://***@#')"
DATABASE_URL="$VERIFY" python -c 'from app.config import get_settings; u=get_settings().database_url; assert u.endswith("/concierge_twobiz_verify"), "REFUSING: not the throwaway db: "+u.rsplit("/",1)[-1]; print("confirmed throwaway target")'
DATABASE_URL="$VERIFY" python /tmp/twobiz_e2e.py
