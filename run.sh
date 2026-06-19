#!/bin/bash
# Manual start for the Claude bar (install.sh sets up auto-start instead).
cd "$HOME/.truehue-usage" || exit 1
PY="$HOME/.truehue-usage/venv/bin/python3"; [ -x "$PY" ] || PY="python3"
pkill -f claude_overlay_app.py 2>/dev/null; sleep 0.3
nohup bash -c "cd \"$HOME/.truehue-usage\"; while true; do \"$PY\" claude_overlay_app.py; [ \$? -eq 0 ] && break; sleep 2; done" > /tmp/truehue-claude.log 2>&1 &
echo "Claude overlay started. Stop: pkill -f claude_overlay_app.py"
