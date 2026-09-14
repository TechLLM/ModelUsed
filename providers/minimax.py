"""MiniMax 코딩 플랜 — opencode에 등록된 API 키 사용."""
from . import base

AUTH_PATH = "~/.local/share/opencode/auth.json"
URL = "https://api.minimax.io/v1/api/openplatform/coding_plan/remains"


def collect():
    auth = base.read_json(AUTH_PATH)
    key = (auth.get("minimax-coding-plan") or {}).get("key")
    if not key:
        raise base.CollectError("API 키 없음")
    data, stale = base.cached_fetch("minimax_usage", lambda: base.http_get(
        URL, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}))
    windows = []
    for m in data.get("model_remains") or []:
        name = m.get("model_name") or "모델"
        name = "전체" if name == "general" else name
        if m.get("current_interval_remaining_percent") is not None:
            windows.append(base.win(
                f"{name}-5h", f"{name} 5시간",
                100 - m["current_interval_remaining_percent"],
                (m.get("end_time") or 0) / 1000 or None))
        if m.get("current_weekly_remaining_percent") is not None:
            windows.append(base.win(
                f"{name}-7d", f"{name} 주간",
                100 - m["current_weekly_remaining_percent"],
                (m.get("weekly_end_time") or 0) / 1000 or None))
    return base.provider("minimax", "MiniMax", plan="Coding Plan",
                         windows=windows, stale_age=stale)
