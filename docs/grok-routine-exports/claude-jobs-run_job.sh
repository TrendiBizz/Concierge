#!/usr/bin/env bash
# run_job.sh <job>  -- run one headless Claude Code job on Jo's Claude subscription.
# Prompt: prompts/<job>.md   Optional settings: jobs/<job>.conf (MAX_TURNS, TIMEOUT_MIN, ONE_SHOT)
# Log:    logs/<job>_<YYYYmmdd_HHMMSS>.log (capped)   Report: results/<job>_<YYYY-mm-dd>.md
set -uo pipefail
BASE=/workspace/claude-jobs
JOB=${1:?usage: run_job.sh <job>}
case "$JOB" in *[!a-z0-9-]*) echo "bad job name" >&2; exit 2;; esac
PROMPT=$BASE/prompts/$JOB.md
[ -f "$PROMPT" ] || { echo "no prompt $PROMPT" >&2; exit 2; }
export TZ=Pacific/Auckland HOME=/home/box
export PATH=/home/box/.local/bin:/usr/local/bin:/usr/bin:/bin
MAX_TURNS=60; TIMEOUT_MIN=90; ONE_SHOT=0; LOG_CAP_BYTES=$((2*1024*1024))
[ -f "$BASE/jobs/$JOB.conf" ] && . "$BASE/jobs/$JOB.conf"
TS=$(date +%Y%m%d_%H%M%S); DAY=$(date +%F)
mkdir -p "$BASE/logs" "$BASE/results" "$BASE/state" "$BASE/work"
LOG=$BASE/logs/${JOB}_${TS}.log
RESULT=$BASE/results/${JOB}_${DAY}.md
DONE=$BASE/state/$JOB.done
log(){ echo "[$(date '+%F %T %Z')] $*" >>"$LOG"; }

if [ "$ONE_SHOT" = 1 ] && [ -f "$DONE" ]; then log "one-shot job already done ($(cat "$DONE")); skipping"; exit 0; fi

# One job at a time across ALL jobs. Wait up to 2 h for a running job, then give up.
exec 8>"$BASE/state/run.lock"
if ! flock -w 7200 8; then log "another job held the lock for 2 h; skipped"; exit 3; fi

# Claude subscription token (never printed). Not needed if `claude` is logged in another way.
[ -f /home/box/.claude_oauth_env ] && . /home/box/.claude_oauth_env

log "start job=$JOB max_turns=$MAX_TURNS timeout=${TIMEOUT_MIN}m result=$RESULT"
FULL_PROMPT="$( { [ "$JOB" != smoke-test ] && cat "$BASE/prompts/_common.md"; echo; cat "$PROMPT"; } | sed -e "s|@@RESULT_FILE@@|$RESULT|g" -e "s|@@DATE@@|$DAY|g" -e "s|@@TS@@|$TS|g" -e "s|@@WORK@@|$BASE/work/${JOB}_${TS}|g")"
cd "$BASE"
ALLOW=(Bash Read Write Edit Glob Grep WebSearch WebFetch TodoWrite)
# Hard denies on top of the prompt rules: no sudo, no merge, no force push, nothing to the retired box.
DENY=("Bash(sudo:*)" "Bash(gh pr merge:*)" "Bash(git push --force:*)" "Bash(git push -f:*)" "Bash(ssh omega-vps:*)" "Bash(scp omega-vps:*)" "Bash(ssh trader@45.85.3.79:*)")
# No --model / --fallback-model: the subscription default is used, no switching.
timeout -k 60 "${TIMEOUT_MIN}m" claude -p "$FULL_PROMPT" \
    --max-turns "$MAX_TURNS" \
    --output-format text \
    --permission-mode acceptEdits \
    --allowedTools "${ALLOW[@]}" \
    --disallowedTools "${DENY[@]}" \
    --add-dir "$BASE" --add-dir /workspace/claude-jobs/repo \
    < /dev/null 2>&1 | head -c "$LOG_CAP_BYTES" >>"$LOG"
RC=${PIPESTATUS[0]}
log "claude exit=$RC (124=timeout)"

if [ ! -s "$RESULT" ]; then
  { echo "# $JOB $DAY — NO REPORT WRITTEN"; echo; echo "claude exit code: $RC (124 = timed out after ${TIMEOUT_MIN} min)."; echo "Log: $LOG"; echo; echo '```'; tail -n 40 "$LOG"; echo '```'; echo; echo "NEXT: Jo | FILE: $LOG @ n/a | VERDICT: JOB FAILED | DEPLOY: NO"; } >"$RESULT"
  log "wrote failure stub to $RESULT"
fi
[ "$ONE_SHOT" = 1 ] && [ "$RC" = 0 ] && echo "$TS" >"$DONE"

"$BASE/bin/deliver.sh" "$RESULT" >>"$LOG" 2>&1
# housekeeping: logs > 60 days, job worktrees > 14 days
find "$BASE/logs" -name '*.log' -mtime +60 -delete 2>/dev/null
find "$BASE/work" -mindepth 1 -maxdepth 1 -mtime +14 -exec rm -rf {} + 2>/dev/null
log "end"
exit $RC
