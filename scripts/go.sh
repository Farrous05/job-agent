#!/usr/bin/env bash
# One command for a whole job run:
#   1. get the latest version   2. Claude runs /job-run (you watch and approve)
#   3. when you quit Claude: results are saved to GitHub   4. the job page opens
# Usage: scripts/go.sh                 everything except the LinkedIn job search (outreach still runs)
#        scripts/go.sh full            everything, including the LinkedIn job search
#        scripts/go.sh skip-outreach   any /job-run arguments (LinkedIn job search then runs unless you add skip-linkedin)
set -uo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
  page|open|jobs)   # open the job page (always on after install_mac.sh; started here if not)
    if curl -s -o /dev/null http://127.0.0.1:8765/ 2>/dev/null; then
      open "http://127.0.0.1:8765/" 2>/dev/null || xdg-open "http://127.0.0.1:8765/" 2>/dev/null || echo "Open http://127.0.0.1:8765/"
    else
      python3 -m jobagent view
    fi
    exit 0 ;;
  auto)             # same as the daily run / Telegram /run: no questions, summary on Telegram
    echo "Running the job search by itself (20-40 min). Watch it:  tail -f data/logs/$(date +%F).log"
    git pull -q --no-rebase --no-edit || true
    JOBAGENT_MODE=claude JOBAGENT_TRIGGER="findjobs auto" bash scripts/run_scheduled.sh
    echo "Done. Open the jobs:  findjobs page"
    exit 0 ;;
  log)   tail -f "data/logs/$(date +%F).log"; exit 0 ;;
  apply|prep)
    shift_arg="${*:2}"; [ -z "$shift_arg" ] && { echo "Usage: findjobs $1 <company>"; exit 1; }
    claude "/$1 $shift_arg"; python3 -m jobagent save -m "$1 $shift_arg" >/dev/null; exit 0 ;;
  help|-h|--help)
    cat <<'TXT'
findjobs               full search with Claude on screen (you watch), then opens the job page
findjobs auto          full search by itself, no questions (same as the daily run); summary on Telegram
findjobs page          open the job page (all jobs, filters, your applications, CV)
findjobs log           follow today's run log
findjobs apply <co>    draft a cover letter + answers       findjobs prep <co>   interview prep pack
findjobs full          like findjobs, plus the LinkedIn job search
TXT
    exit 0 ;;
esac
args="${*:-skip-linkedin}"
[ "$args" = "full" ] && args=""
echo "Getting the latest version..."
git pull -q --no-rebase --no-edit || echo "(couldn't pull; continuing with what you have)"
echo "Starting Claude. When it has finished, type /exit (or press Ctrl+C twice) to save and open the job page."
claude --chrome "/job-run $args"
echo "Saving your results..."
python3 -m jobagent save -m "Job run $(date +%F)"
echo "Sending the summary to your phone..."
python3 -m jobagent notify || true
echo "Opening the job page (press Ctrl+C here when you're done; your marks are saved and pushed automatically)."
python3 -m jobagent view
