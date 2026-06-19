#!/usr/bin/env python3
"""truHue · Claude usage — title-bar overlay (launcher).

Independent of the Codex bar. Pins a usage panel to the Claude desktop window and
follows it. Run: ./run.sh
"""
import datetime as dt
import truehue_usage as tu
import overlay_core as core


def render(status):
    """Claude status -> (compact title-bar line, full hover tooltip)."""
    plan = (status or {}).get("plan") or {}
    local = (status or {}).get("local") or {}
    if "error" in plan:
        return "Claude ⚠", plan["error"]
    metrics = plan.get("metrics") or []
    spend = plan.get("spend")

    parts, tip = [], ["Claude · plan usage"]
    for m in metrics:
        pct = m.get("percent")
        seg = f"{core.dot(pct, m.get('severity'))} {core.SHORT.get(m.get('kind'), m.get('kind','?'))} {pct}%"
        if m.get("kind") == "session":  # show when the 5-hour window resets, like the usage page
            rs = core.reset_short(m.get("resets_at"))
            if rs:
                seg += f" ↻{rs}"
        parts.append(seg)
        star = " ●" if m.get("active") else ""
        r = core.reset(m.get("resets_at"))
        tip.append(f"{core.dot(pct, m.get('severity'))} {m['label']}: {pct}%{star}" + (f"   ·  {r}" if r else ""))
    if spend:
        cur = "$" if spend.get("currency") == "USD" else (spend.get("currency", "") + " ")
        parts.append(f"💳 {cur}{spend['used']:.2f}")
        tip.append(f"💳 {spend['label']}: {cur}{spend['used']:.2f} / {cur}{spend['limit']:.2f} ({spend.get('percent')}%)")
    tip.append(f"⌨ Claude Code (this Mac): {core.htok(local.get('today_tokens'))} today · "
               f"{core.htok(local.get('week_tokens'))} 7d")
    at = (status or {}).get("at", "")
    try:
        at = dt.datetime.fromisoformat(at).strftime("%H:%M:%S")
    except Exception:
        pass
    tip.append(f"updated {at}  ·  right-click for options")
    line = "   ".join(parts) if parts else "Claude –"
    return line, "\n".join(tip)


if __name__ == "__main__":
    core.run({
        "name": "Claude",
        "bundle_id": "com.anthropic.claudefordesktop",
        "owner": "Claude",
        "right_extra": 250.0,  # shift left to clear the title-bar buttons (drag to fine-tune)
        "poll_seconds": 60,
        "fetch": tu.get_status,
        "render": render,
    })
