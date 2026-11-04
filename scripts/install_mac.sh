#!/usr/bin/env bash
# One-command setup of everything that runs by itself on your Mac:
#   1. daily job search at 08:40 (Claude scores everything; summary to Telegram)
#   2. the Telegram bot (your phone remote: /jobs /cv /changes /apply /run ...), always on
#   3. the job page, always on, reachable from your phone on home Wi-Fi via a private link
# Usage:  scripts/install_mac.sh            install / update all three
#         scripts/install_mac.sh --uninstall stop and remove them
set -uo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"
AGENTS="$HOME/Library/LaunchAgents"
LABELS=(com.fares.jobagent com.fares.jobagent.bot com.fares.jobagent.page)
PATH_LINE="/opt/homebrew/bin:/usr/local/bin:/Library/TeX/texbin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

if [ "${1:-}" = "--uninstall" ]; then
  for l in "${LABELS[@]}"; do launchctl unload "$AGENTS/$l.plist" 2>/dev/null; rm -f "$AGENTS/$l.plist"; done
  echo "Removed the daily run, the bot and the always-on job page."
  exit 0
fi

PY="$(PATH="$PATH_LINE" command -v python3)"
if ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
  echo "Needs Python 3.11+ ($PY is $("$PY" --version 2>&1)). Run: brew install python"; exit 1
fi
mkdir -p "$AGENTS" data/logs

plist() {  # label, keepalive(true/false), program args..., (calendar handled separately)
  local label="$1" keep="$2"; shift 2
  local args=""; for a in "$@"; do args+="    <string>$a</string>
"; done
  cat > "$AGENTS/$label.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>ProgramArguments</key>
  <array>
$args  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>$PATH_LINE</string>
    <key>JOBAGENT_MODE</key><string>claude</string>
  </dict>
  <key>StandardOutPath</key><string>$REPO/data/logs/$label.log</string>
  <key>StandardErrorPath</key><string>$REPO/data/logs/$label.log</string>
EOF
  if [ "$keep" = "true" ]; then
    printf '  <key>RunAtLoad</key><true/>\n  <key>KeepAlive</key><true/>\n' >> "$AGENTS/$label.plist"
  else
    printf '  <key>StartCalendarInterval</key>\n  <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>40</integer></dict>\n' >> "$AGENTS/$label.plist"
  fi
  printf '</dict>\n</plist>\n' >> "$AGENTS/$label.plist"
  launchctl unload "$AGENTS/$label.plist" 2>/dev/null
  launchctl load "$AGENTS/$label.plist"
}

plist com.fares.jobagent false /bin/bash "$REPO/scripts/run_scheduled.sh"
echo "✓ Daily job search: every day at 08:40 (or when the Mac wakes)."

plist com.fares.jobagent.page true "$PY" -m jobagent view --lan --autosave --no-open --no-git
sleep 2
LINK="$("$PY" -c 'from pathlib import Path; from jobagent.server import phone_link; print(phone_link(Path(".")))')"
echo "✓ Job page, always on:  http://127.0.0.1:8765/   (on this Mac)"
echo "  On your phone (same Wi-Fi), keep it private:  $LINK"

if [ -f config/telegram.json ]; then
  plist com.fares.jobagent.bot true "$PY" -m jobagent bot
  echo "✓ Telegram bot, always on: send /help to your bot."
else
  echo "✗ Telegram bot not started: run  python3 -m jobagent notify-setup --telegram  then this script again."
fi
echo
echo "macOS may ask once to allow incoming connections for Python: click Allow (that's the phone link)."
echo "Logs: data/logs/. Stop everything: scripts/install_mac.sh --uninstall"
