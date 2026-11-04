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
    # strip the --- front matter (awk: works the same on macOS and Linux)
    prompt="$(awk 'n>=2 {print; next} /^---$/ {n++}' .claude/commands/job-run.md)"
    claude -p "Arguments: skip-outreach skip-cv skip-linkedin
$prompt" \
      --allowedTools "Bash(python3 -m jobagent:*)" "Bash(date:*)" "Bash(ls:*)" "Bash(cat:*)" "Bash(head:*)" \
        "Bash(wc:*)" "Bash(mkdir:*)" "WebSearch" "WebFetch" "Read" "Glob" "Grep" "Task" "Agent" \
        "Edit(shortlist/**)" "Edit(data/**)" \
      --permission-mode acceptEdits
  else
    python3 -m jobagent run
  fi
} >>"$log" 2>&1
# save results to GitHub (new shortlist, scores, marks)
python3 -m jobagent save -m "Scheduled run" >>"$log" 2>&1 || true
# macOS notification with reminders (deadlines closing soon, follow-ups due); ignored elsewhere
rem="$(python3 -m jobagent reminders 2>/dev/null | head -3 | tr '\n' ' ' | tr -d '"')"
command -v osascript >/dev/null && osascript -e "display notification \"New jobs ready. ${rem}\" with title \"Job agent\"" || true
