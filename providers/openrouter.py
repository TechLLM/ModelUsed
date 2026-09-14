"""OpenRouter — 크레딧/월간 한도."""
from . import base

AUTH_PATH = "~/.local/share/opencode/auth.json"
CREDITS_URL = "https://openrouter.ai/api/v1/credits"
KEY_URL = "https://openrouter.ai/api/v1/auth/key"


def collect():
    auth = base.read_json(AUTH_PATH)
    key = (auth.get("openrouter") or {}).get("key")
    if not key:
        raise base.CollectError("API 키 없음")
    h = {"Authorization": f"Bearer {key}"}
    credits, stale = base.cached_fetch(
        "openrouter_credits", lambda: base.http_get(CREDITS_URL, h))
    credits = credits.get("data") or {}
    keyinfo, _ = base.cached_fetch(
        "openrouter_key", lambda: base.http_get(KEY_URL, h), ttl=3600)
    keyinfo = keyinfo.get("data") or {}

    windows = []
    total, used = credits.get("total_credits"), credits.get("total_usage")
    if total:
        pct = (used or 0) / total * 100
        windows.append(base.win(
            "credits", "크레딧", pct, None,
            f"잔액 ${max(total - (used or 0), 0):.2f} / ${total:.0f}"))

    limit = keyinfo.get("limit")
    remaining = keyinfo.get("limit_remaining")
    if limit and remaining is not None:
        pct = (limit - remaining) / limit * 100
        resets = None
        if keyinfo.get("limit_reset") == "monthly":
            from datetime import datetime, timezone
            t = datetime.now(timezone.utc)
            nxt = datetime(t.year + (t.month == 12), (t.month % 12) + 1, 1)
            resets = nxt.timestamp()
        windows.append(base.win(
            "monthly-limit", "월간 한도", pct, resets,
            f"${limit - remaining:.2f} / ${limit:.0f}"))

    billing = None
    if keyinfo.get("limit_reset"):
        billing = {"cycle": keyinfo["limit_reset"], "next_date": None,
                   "label": f"한도 리셋: {keyinfo['limit_reset']}"}
    return base.provider("openrouter", "OpenRouter", plan="API",
                         windows=windows, billing=billing, stale_age=stale)
