#!/bin/bash
# Manual start for the Codex bar (install.sh sets up auto-start instead).
cd "$HOME/.truehue-usage" || exit 1
PY="$HOME/.truehue-usage/venv/bin/python3"; [ -x "$PY" ] || PY="python3"
pkill -f codex_overlay_app.py 2>/dev/null; sleep 0.3
nohup bash -c "cd \"$HOME/.truehue-usage\"; while true; do \"$PY\" codex_overlay_app.py; [ \$? -eq 0 ] && break; sleep 2; done" > /tmp/truehue-codex.log 2>&1 &
echo "Codex overlay started. Stop: pkill -f codex_overlay_app.py"
