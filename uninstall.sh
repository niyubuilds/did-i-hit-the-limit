#!/bin/bash
# truHue usage bars — uninstaller.
LA="$HOME/Library/LaunchAgents"
for l in ai.truehue.claude ai.truehue.codex; do
  launchctl unload "$LA/$l.plist" 2>/dev/null || true
  rm -f "$LA/$l.plist"
done
pkill -f claude_overlay_app.py 2>/dev/null || true
pkill -f codex_overlay_app.py 2>/dev/null || true
echo "✓ Stopped the bars and disabled auto-start."
printf "Also delete ~/.truehue-usage (app + venv)? [y/N] "
read -r a
if [ "$a" = "y" ] || [ "$a" = "Y" ]; then
  rm -rf "$HOME/.truehue-usage" && echo "✓ Removed ~/.truehue-usage."
else
  echo "Kept files at ~/.truehue-usage."
fi
echo "No system files or keychain entries were modified by this tool."
