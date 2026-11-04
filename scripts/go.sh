#!/usr/bin/env bash
# One command for a whole job run:
#   1. get the latest version   2. Claude runs /job-run (you watch and approve)
#   3. when you quit Claude: results are saved to GitHub   4. the job page opens
# Usage: scripts/go.sh                 everything except the LinkedIn job search (outreach still runs)
#        scripts/go.sh full            everything, including the LinkedIn job search
#        scripts/go.sh skip-outreach   any /job-run arguments (LinkedIn job search then runs unless you add skip-linkedin)
set -uo pipefail
cd "$(dirname "$0")/.."
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
