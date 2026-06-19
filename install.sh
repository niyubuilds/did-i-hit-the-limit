#!/bin/bash
# truHue usage bars — one-command installer (macOS).
# Installs into ~/.truehue-usage with a self-contained venv, then runs the bars
# and sets them to auto-start at login. Re-runnable. Uninstall: ./uninstall.sh
set -e

DEST="$HOME/.truehue-usage"
SRC="$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)"
PYBIN="$DEST/venv/bin/python3"
REPO="https://github.com/niyubuilds/did-i-hit-the-limit.git"
LA="$HOME/Library/LaunchAgents"
b="\033[1m"; g="\033[1;32m"; y="\033[1;33m"; off="\033[0m"

[ "$(uname)" = "Darwin" ] || { echo "This tool is macOS-only."; exit 1; }
command -v python3 >/dev/null || { echo "Python 3 is required. Install it: brew install python (or python.org)"; exit 1; }

echo -e "${b}truHue usage bars — installing…${off}"

# 0) if run standalone (curl | bash), fetch the source first
if [ -z "$SRC" ] || [ ! -f "$SRC/claude_overlay_app.py" ]; then
  command -v git >/dev/null || { echo "git is required (run: xcode-select --install)"; exit 1; }
  SRC="$HOME/.truehue-usage-src"; rm -rf "$SRC"
  echo "  • fetching source…"; git clone --depth 1 "$REPO" "$SRC" >/dev/null 2>&1
fi

# 1) files → ~/.truehue-usage
mkdir -p "$DEST"
if [ "$SRC" != "$DEST" ]; then
  cp "$SRC"/*.py "$DEST"/
  cp "$SRC"/run.sh "$SRC"/run-codex.sh "$DEST"/ 2>/dev/null || true
fi
chmod +x "$DEST"/run.sh "$DEST"/run-codex.sh 2>/dev/null || true

# 2) isolated venv with deps (won't touch their system Python)
echo "  • setting up Python environment…"
[ -x "$PYBIN" ] || python3 -m venv "$DEST/venv"
"$PYBIN" -m pip install --quiet --upgrade pip
"$PYBIN" -m pip install --quiet pyobjc-core pyobjc-framework-Cocoa pycryptodome curl_cffi

# 3) auto-start at login (launchd KeepAlive restarts on crash, not on Quit)
mkdir -p "$LA"
make_agent() {  # $1=label  $2=script
  cat > "$LA/$1.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$1</string>
  <key>ProgramArguments</key><array><string>$PYBIN</string><string>$DEST/$2</string></array>
  <key>WorkingDirectory</key><string>$DEST</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>StandardOutPath</key><string>/tmp/$1.log</string>
  <key>StandardErrorPath</key><string>/tmp/$1.log</string>
</dict></plist>
PLIST
  launchctl unload "$LA/$1.plist" 2>/dev/null || true
  launchctl load "$LA/$1.plist"
}
echo "  • enabling auto-start at login…"
make_agent ai.truehue.claude claude_overlay_app.py
make_agent ai.truehue.codex  codex_overlay_app.py

echo -e "${g}✓ Installed.${off}"
echo -e "The bars appear at the top-right of the ${b}Claude${off} / ${b}Codex${off} windows when each is in front."
echo -e "${y}First run shows ONE macOS keychain prompt (\"Claude Safe Storage\") — click Allow; it's cached after that.${off}"
echo "Drag a bar to reposition · right-click for Refresh/Quit · uninstall with ./uninstall.sh"
