#!/usr/bin/env bash
# Scheduled run (launchd/cron). Two modes, set JOBAGENT_MODE:
#   script (default) : python fetcher + keyword ranking only. Free, no Claude.
#   claude           : headless Claude Code runs the job-run command without outreach (uses your Claude plan).
# Outreach (LinkedIn) is never scheduled. Run /outreach yourself in an interactive `claude --chrome` session.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/TeX/texbin:$HOME/.local/bin:$PATH"
mkdir -p data/logs
# only one run at a time (the 08:40 run and a /run from your phone could overlap)
if ! mkdir data/run.lock 2>/dev/null; then
  if [ -n "$(find data/run.lock -maxdepth 0 -mmin -180 2>/dev/null)" ]; then
    echo "A run is already in progress; not starting another." | tee -a "data/logs/$(date +%F).log"; exit 0
  fi
  rm -rf data/run.lock && mkdir data/run.lock     # stale lock (older than 3 h): take over
fi
trap 'rm -rf data/run.lock' EXIT
log="data/logs/$(date +%F).log"
[ "${JOBAGENT_TRIGGER:-}" = "com.fares.jobagent" ] && JOBAGENT_TRIGGER="the daily 08:40 schedule"
{
  echo "=== $(date) mode=${JOBAGENT_MODE:-script} started by: ${JOBAGENT_TRIGGER:-hand}"
  if [ "${JOBAGENT_MODE:-script}" = "claude" ]; then
    # strip the --- front matter (awk: works the same on macOS and Linux)
    prompt="$(awk 'n>=2 {print; next} /^---$/ {n++}' .claude/commands/job-run.md)"
    # fetch here first (Claude in -p mode loses background work), then Claude does the rest
    echo "--- fetch"
    if ! python3 -m jobagent run --dry-run; then
      echo "!!! fetch failed"
    else
    echo "--- claude"
    export CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0     # if it does start background work, wait for it
    claude -p "Arguments: already-fetched skip-outreach skip-cv skip-linkedin
You are running unattended: run every command in the foreground and wait for it; never use background
tasks or monitors.
$prompt" \
      --allowedTools "Bash(python3 -m jobagent:*)" "Bash(date:*)" "Bash(ls:*)" "Bash(cat:*)" "Bash(head:*)" \
        "Bash(wc:*)" "Bash(mkdir:*)" "WebSearch" "WebFetch" "Read" "Glob" "Grep" "Task" "Agent" \
        "Edit(shortlist/**)" "Edit(data/**)" \
      --permission-mode acceptEdits || echo "!!! claude exited with code $?"
    fi
  else
    python3 -m jobagent run || echo "!!! jobagent run exited with code $?"
  fi
  echo "=== $(date) finished"
} >>"$log" 2>&1
# save results to GitHub (new shortlist, scores, marks)
python3 -m jobagent save -m "Scheduled run" >>"$log" 2>&1 || true
# phone notification (if set up with `python3 -m jobagent notify-setup`). If no shortlist was written today,
# the run didn't finish: say so (with the end of the log) instead of a normal "no new picks" summary.
if ls shortlist/"$(date +%F)"*.md >/dev/null 2>&1; then
  python3 -m jobagent notify >>"$log" 2>&1 || true
else
  tailtxt="$(grep -v '^\s*$' "$log" | tail -6 | cut -c1-200)"
  python3 -m jobagent notify "⚠ The job search (started by ${JOBAGENT_TRIGGER:-hand}) did not finish, so there are no new picks. End of the log (data/logs/$(date +%F).log):
$tailtxt
Common fixes: Claude login expired (open Terminal, run claude, then /login), or send /run to try again." >>"$log" 2>&1 || true
fi
# macOS notification with reminders (deadlines closing soon, follow-ups due); ignored elsewhere
rem="$(python3 -m jobagent reminders 2>/dev/null | head -3 | tr '\n' ' ' | tr -d '"')"
command -v osascript >/dev/null && osascript -e "display notification \"New jobs ready. ${rem}\" with title \"Job agent\"" || true
