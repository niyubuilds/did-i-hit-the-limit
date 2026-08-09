#!/usr/bin/env python3
"""Claude plan-usage data (for the title-bar overlay).

Reads the usage the Claude desktop app records locally at
   ~/Library/Application Support/Claude/plan-usage-history.json
(a {version, samples:[{t, org, u:{fh, sd, xu}}]} time series it keeps itself).
Using this local file means NO cookies, NO Cloudflare, NO keychain prompt, and it
keeps working across app updates that move the session store — which the older
cookie+API approach did not.

  fh = 5-hour (session) %,  sd = 7-day (weekly) %,  xu = extra-usage %.

Reset times and per-model breakdowns aren't in the file, so those aren't shown.
Claude Code token totals still come from ~/.claude/projects/*.jsonl.
"""
import json, os, glob, datetime as dt

HISTORY = os.path.expanduser("~/Library/Application Support/Claude/plan-usage-history.json")


def _num(x):
    try:
        return round(float(x))
    except (TypeError, ValueError):
        return None


def fetch_plan_usage():
    if not os.path.exists(HISTORY):
        return {"error": "No Claude usage file yet — open Claude once."}
    try:
        with open(HISTORY) as f:
            samples = (json.load(f) or {}).get("samples") or []
        if not samples:
            return {"error": "Claude hasn't recorded usage yet."}
        u = samples[-1].get("u") or {}
    except (ValueError, OSError) as e:
        return {"error": f"usage file: {e}"}

    metrics = []
    if u.get("fh") is not None:
        metrics.append({"kind": "session", "label": "Session (5-hour)",
                        "percent": _num(u["fh"]), "severity": "normal",
                        "resets_at": None, "active": True})
    if u.get("sd") is not None:
        metrics.append({"kind": "weekly_all", "label": "Weekly",
                        "percent": _num(u["sd"]), "severity": "normal",
                        "resets_at": None, "active": False})
    spend = None
    if _num(u.get("xu")):  # only when extra usage is actually non-zero
        spend = {"label": "Extra usage", "percent": _num(u["xu"]), "severity": "normal"}
    return {"metrics": metrics, "spend": spend}


def fetch_local_usage():
    base = os.path.expanduser("~/.claude/projects")
    today = dt.datetime.now().date()
    week_ago = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)
    today_tok = week_tok = today_msgs = 0
    for f in glob.glob(os.path.join(base, "**", "*.jsonl"), recursive=True):
        try:
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    msg = d.get("message") if isinstance(d.get("message"), dict) else None
                    us = (msg or {}).get("usage") or d.get("usage")
                    if not us:
                        continue
                    tok = (us.get("input_tokens", 0) + us.get("output_tokens", 0)
                           + us.get("cache_creation_input_tokens", 0)
                           + us.get("cache_read_input_tokens", 0))
                    ts = d.get("timestamp")
                    tdt = None
                    if ts:
                        try:
                            tdt = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        except ValueError:
                            tdt = None
                    if tdt and tdt >= week_ago:
                        week_tok += tok
                    if tdt and tdt.astimezone().date() == today:
                        today_tok += tok; today_msgs += 1
        except OSError:
            continue
    return {"today_tokens": today_tok, "week_tokens": week_tok, "today_msgs": today_msgs}


def get_status():
    try:
        plan = fetch_plan_usage()
    except Exception as e:
        plan = {"error": str(e)}
    try:
        local = fetch_local_usage()
    except Exception:
        local = {}
    return {"plan": plan, "local": local, "at": dt.datetime.now().isoformat()}


if __name__ == "__main__":
    print(json.dumps(get_status(), indent=2))
