#!/usr/bin/env python3
"""truHue · Codex usage — title-bar overlay (launcher).

Pins a usage panel to the Codex desktop window (com.openai.codex), shown only
while Codex is frontmost. Same UI as the Claude bar. Run:  ./run-codex.sh
"""
import os, datetime as dt
import codex_usage as cu
import overlay_core as core

HERE = os.path.dirname(os.path.abspath(__file__))


def render(status):
    """Codex status -> (compact title-bar line, full hover tooltip)."""
    plan = (status or {}).get("plan") or {}
    if "error" in plan:
        return "Codex ⚠", plan["error"]
    metrics = plan.get("metrics") or []
    PLAN_NAMES = {"prolite": "Pro", "pro": "Pro", "plus": "Plus", "free": "Free", "team": "Team"}
    head = "Codex · plan usage"
    if plan.get("plan_type"):
        head += f" ({PLAN_NAMES.get(plan['plan_type'], plan['plan_type'].title())})"
    parts, tip = [], [head]
    for m in metrics:
        pct = m.get("percent")
        seg = f"{core.dot(pct)} {core.SHORT.get(m.get('kind'), m.get('kind','?'))} {pct}%"
        if m.get("kind") == "session":  # when the 5-hour window resets
            rs = core.reset_short(m.get("resets_at"))
            if rs:
                seg += f" ↻{rs}"
        parts.append(seg)
        r = core.reset(m.get("resets_at"))
        tip.append(f"{core.dot(pct)} {m['label']}: {pct}%" + (f"   ·  {r}" if r else ""))
    for e in (plan.get("extra_models") or []):
        tip.append(f"   ↳ {e['name']}: 5h {e['p']}% · wk {e['s']}%")
    # Codex on a ChatGPT plan has no billing — no "$"/credits line on the bar.
    rc = plan.get("reset_credits")
    if rc:
        tip.append(f"♻ limit-reset credits available: {rc}")
    if plan.get("blocked"):
        tip.append("⛔ rate limit reached")
    at = (status or {}).get("at", "")
    try:
        at = dt.datetime.fromisoformat(at).strftime("%H:%M:%S")
    except Exception:
        pass
    tip.append(f"updated {at}  ·  right-click for options")
    line = "   ".join(parts) if parts else "Codex –"
    return line, "\n".join(tip)


if __name__ == "__main__":
    core.run({
        "name": "Codex",
        "bundle_id": "com.openai.codex",
        "owner": "Codex",
        "right_extra": 140.0,  # shift left ~4 title-bar buttons
        "poll_seconds": 60,
        "fetch": cu.get_status,
        "render": render,
    })
