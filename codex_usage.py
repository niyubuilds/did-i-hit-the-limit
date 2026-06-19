#!/usr/bin/env python3
"""Codex (ChatGPT-plan) usage data.

Reads the access token from ~/.codex/auth.json (a plain 0600 file Codex keeps
fresh — no keychain, no password prompts) and calls the official usage endpoint
   GET https://chatgpt.com/backend-api/wham/usage
which returns the 5-hour (primary) and weekly (secondary) rate-limit windows,
per-model limits, and credit balance.
"""
import json, os, datetime as dt
from curl_cffi import requests as creq

AUTH = os.path.expanduser("~/.codex/auth.json")
USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _read_auth():
    a = json.load(open(AUTH))
    t = a.get("tokens") or {}
    tok = t.get("access_token")
    if not tok:
        raise RuntimeError("No Codex ChatGPT login (API-key mode has no % limits).")
    return tok, t.get("account_id")


def _num(x):
    try:
        return round(float(x))
    except (TypeError, ValueError):
        return None


def _win(w, kind, label):
    if not w:
        return None
    rs = w.get("reset_at")
    iso = dt.datetime.fromtimestamp(rs, dt.timezone.utc).isoformat() if rs else None
    return {"kind": kind, "label": label, "percent": _num(w.get("used_percent")),
            "severity": "normal", "resets_at": iso, "active": False}


def parse_usage(j):
    rl = j.get("rate_limit") or {}
    metrics = []
    for win, kind, label in ((rl.get("primary_window"), "session", "Session (5-hour)"),
                             (rl.get("secondary_window"), "weekly_all", "Weekly")):
        m = _win(win, kind, label)
        if m:
            metrics.append(m)
    extra = []
    for a in (j.get("additional_rate_limits") or []):
        arl = a.get("rate_limit") or {}
        extra.append({
            "name": a.get("limit_name") or a.get("metered_feature") or "model",
            "p": _num((arl.get("primary_window") or {}).get("used_percent")),
            "s": _num((arl.get("secondary_window") or {}).get("used_percent")),
        })
    credits = j.get("credits") or {}
    bal = credits.get("balance")
    cr = {"balance": bal, "unlimited": credits.get("unlimited")} \
        if (credits.get("has_credits") or bal not in (None, "0", 0)) else None
    return {
        "metrics": metrics, "extra_models": extra, "credits": cr,
        "plan_type": j.get("plan_type"),
        "reset_credits": (j.get("rate_limit_reset_credits") or {}).get("available_count"),
        "blocked": bool(rl.get("limit_reached")),
    }


def fetch_usage():
    tok, acct = _read_auth()
    headers = {"Authorization": "Bearer " + tok, "chatgpt-account-id": acct or "",
               "Accept": "application/json", "User-Agent": UA}
    r = creq.get(USAGE_URL, headers=headers, impersonate="chrome", timeout=25)
    if r.status_code == 401:
        return {"error": "Codex login expired — open Codex once to refresh."}
    if r.status_code != 200:
        return {"error": f"usage API {r.status_code}"}
    return parse_usage(r.json())


def get_status():
    try:
        plan = fetch_usage()
    except Exception as e:
        plan = {"error": str(e)}
    return {"plan": plan, "local": {}, "at": dt.datetime.now().isoformat()}


if __name__ == "__main__":
    print(json.dumps(get_status(), indent=2))
