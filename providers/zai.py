"""Z.ai 코딩 플랜 (GLM) — opencode에 등록된 API 키 사용."""
from . import base

AUTH_PATH = "~/.local/share/opencode/auth.json"
USAGE_URL = "https://api.z.ai/api/monitor/usage/quota/limit"


def _key():
    auth = base.read_json(AUTH_PATH)
    for name in ("zai-coding-plan", "zai"):
        k = (auth.get(name) or {}).get("key")
        if k:
            return k
    raise base.CollectError("API 키 없음")


def _label(lim):
    t, u, n = lim.get("type"), lim.get("unit"), lim.get("number")
    if t == "TOKENS_LIMIT" and u == 3:
        return f"{n}시간 토큰"
    if t == "TOKENS_LIMIT" and u == 6:
        return "주간 토큰" if n == 1 else f"{n}주 토큰"
    if t == "TIME_LIMIT":
        return "월간 도구 호출"
    return t or "한도"


def collect():
    key = _key()
    data, stale = base.cached_fetch(
        "zai_usage", lambda: base.http_get(USAGE_URL, {"Authorization": key}))
    d = data.get("data") or {}
    windows = []
    for lim in d.get("limits") or []:
        detail = ""
        if lim.get("usage") and lim.get("currentValue") is not None:
            detail = f"{lim['currentValue']}/{lim['usage']}회"
        windows.append(base.win(
            f"{lim.get('type')}-{lim.get('unit')}", _label(lim),
            lim.get("percentage", 0),
            (lim.get("nextResetTime") or 0) / 1000 or None,
            detail))
    level = d.get("level")
    plan = {"pro": "Pro", "max": "Max", "free": "Free"}.get(level, level)
    return base.provider("zai", "Z.ai (GLM)", plan=plan, windows=windows,
                         stale_age=stale)
