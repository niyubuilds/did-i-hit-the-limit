#!/usr/bin/env python3
"""Claude plan-usage data (for the title-bar overlay).

Reads the live usage the Claude desktop app sees:
  1. Safe-Storage key from the keychain (read once, cached to .keycache → no
     repeat password prompts).
  2. Decrypts the claude.ai cookies from the app's Cookies store.
  3. GET https://claude.ai/api/organizations/{org}/usage  (Chrome TLS via curl_cffi).
  4. Plus this Mac's Claude Code token totals from ~/.claude/projects/*.jsonl.
"""
import subprocess, hashlib, os, sqlite3, shutil, tempfile, json, glob, datetime as dt
from Crypto.Cipher import AES
from curl_cffi import requests as creq

HERE = os.path.dirname(os.path.abspath(__file__))
SAFE_SERVICE = "Claude Safe Storage"
COOKIES_DB = os.path.expanduser("~/Library/Application Support/Claude/Cookies")
_KEY_FILE = os.path.join(HERE, ".keycache")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

KIND_LABELS = {
    "session": "Session (5-hour)", "weekly_all": "Weekly · all models",
    "weekly_opus": "Weekly · Opus", "weekly_sonnet": "Weekly · Sonnet",
    "weekly_cowork": "Weekly · Cowork",
}
BUCKETS = {
    "five_hour": "Session (5-hour)", "seven_day": "Weekly · all models",
    "seven_day_opus": "Weekly · Opus", "seven_day_sonnet": "Weekly · Sonnet",
    "seven_day_cowork": "Weekly · Cowork",
}

_KEY_CACHE = None


def _safe_storage_key():
    return subprocess.run(["security", "find-generic-password", "-s", SAFE_SERVICE, "-w"],
                          capture_output=True, text=True).stdout.strip()


def _derived_key():
    """Cookie-decryption key; keychain is read at most once ever (then .keycache)."""
    global _KEY_CACHE
    if _KEY_CACHE is not None:
        return _KEY_CACHE
    try:
        with open(_KEY_FILE, "rb") as f:
            k = f.read()
        if len(k) == 16:
            _KEY_CACHE = k
            return _KEY_CACHE
    except OSError:
        pass
    _KEY_CACHE = hashlib.pbkdf2_hmac("sha1", _safe_storage_key().encode(), b"saltysalt", 1003, 16)
    try:
        fd = os.open(_KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.write(fd, _KEY_CACHE); os.close(fd)
    except OSError:
        pass
    return _KEY_CACHE


def _decrypt(enc, key):
    if not enc:
        return ""
    if enc[:3] in (b"v10", b"v11"):
        enc = enc[3:]
    d = AES.new(key, AES.MODE_CBC, b" " * 16).decrypt(enc)
    pad = d[-1]
    if 1 <= pad <= 16:
        d = d[:-pad]
    try:
        return d.decode("utf-8")
    except UnicodeDecodeError:
        return d[32:].decode("utf-8", "replace")  # strip Chromium domain-hash prefix


def read_cookies():
    if not os.path.exists(COOKIES_DB):
        raise RuntimeError("Claude cookie store not found — is Claude installed/logged in?")
    key = _derived_key()
    tmp = tempfile.mktemp(suffix=".db")
    shutil.copy(COOKIES_DB, tmp)
    try:
        con = sqlite3.connect(tmp); cur = con.cursor()
        cur.execute("select name, encrypted_value from cookies where host_key like '%claude.ai%'")
        out = {n: _decrypt(e, key) for n, e in cur.fetchall()}
        con.close()
        return out
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _num(x):
    try:
        return round(float(x))
    except (TypeError, ValueError):
        return None


def parse_usage(j):
    metrics = []
    for lim in (j.get("limits") or []):
        kind = lim.get("kind", "")
        metrics.append({
            "kind": kind,
            "label": KIND_LABELS.get(kind, kind.replace("_", " ").title()),
            "percent": _num(lim.get("percent")),
            "severity": lim.get("severity", "normal"),
            "resets_at": lim.get("resets_at"),
            "active": bool(lim.get("is_active")),
        })
    for bucket, label in BUCKETS.items():
        v = j.get(bucket)
        if isinstance(v, dict) and v.get("utilization") is not None \
                and not any(m["label"] == label for m in metrics):
            metrics.append({"kind": bucket, "label": label, "percent": _num(v.get("utilization")),
                            "severity": "normal", "resets_at": v.get("resets_at"), "active": False})

    spend = None
    sp = j.get("spend") or {}
    eu = j.get("extra_usage") or {}
    if sp.get("enabled") or eu.get("is_enabled"):
        used_obj, lim_obj = sp.get("used") or {}, sp.get("limit") or {}
        if used_obj or lim_obj:
            used = used_obj.get("amount_minor", 0) / (10 ** used_obj.get("exponent", 2))
            limit = lim_obj.get("amount_minor", 0) / (10 ** lim_obj.get("exponent", 2))
            cur = used_obj.get("currency") or lim_obj.get("currency") or "USD"
        else:
            dp = eu.get("decimal_places", 2)
            used = (eu.get("used_credits") or 0) / (10 ** dp)
            limit = (eu.get("monthly_limit") or 0) / (10 ** dp)
            cur = eu.get("currency", "USD")
        spend = {"label": "Extra usage", "currency": cur, "used": used, "limit": limit,
                 "percent": _num(sp.get("percent", eu.get("utilization"))),
                 "severity": sp.get("severity", "normal")}
    return {"metrics": metrics, "spend": spend}


def fetch_plan_usage():
    ck = read_cookies()
    org = ck.get("lastActiveOrg")
    if not org:
        return {"error": "No active Claude org — open Claude once."}
    r = creq.get(f"https://claude.ai/api/organizations/{org}/usage",
                 cookies={k: v for k, v in ck.items() if v}, impersonate="chrome", timeout=25,
                 headers={"User-Agent": UA, "Accept": "application/json", "Referer": "https://claude.ai/"})
    if r.status_code in (401, 403):
        return {"error": "Claude session expired — open Claude."}
    if r.status_code != 200:
        return {"error": f"usage API {r.status_code}"}
    return parse_usage(r.json())


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
                    u = (msg or {}).get("usage") or d.get("usage")
                    if not u:
                        continue
                    tok = (u.get("input_tokens", 0) + u.get("output_tokens", 0)
                           + u.get("cache_creation_input_tokens", 0)
                           + u.get("cache_read_input_tokens", 0))
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
