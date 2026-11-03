#!/usr/bin/env bash
# Scheduled run (launchd/cron). Two modes, set JOBAGENT_MODE:
#   script (default) : python fetcher + keyword ranking only. Free, no Claude.
#   claude           : headless Claude Code runs the job-run command without outreach (uses your Claude plan).
# Outreach (LinkedIn) is never scheduled. Run /outreach yourself in an interactive `claude --chrome` session.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/TeX/texbin:$HOME/.local/bin:$PATH"
mkdir -p data/logs
log="data/logs/$(date +%F).log"
{
  echo "=== $(date) mode=${JOBAGENT_MODE:-script}"
  if [ "${JOBAGENT_MODE:-script}" = "claude" ]; then
    prompt="$(sed '1,/^---$/{/^---$/!d}; 1,/^---$/d' .claude/commands/job-run.md)"
    claude -p "Arguments: skip-outreach skip-cv
$prompt" \
      --allowedTools "Bash(python3 -m jobagent:*)" "Bash(date:*)" "WebSearch" "WebFetch" "Read" "Write(shortlist/**)" \
      --permission-mode acceptEdits
  else
    python3 -m jobagent run
  fi
} >>"$log" 2>&1
# macOS notification (ignored elsewhere)
command -v osascript >/dev/null && osascript -e "display notification \"New shortlist in job-agent/shortlist\" with title \"Job agent\"" || true
