"""Codex (ChatGPT) — OpenAI OAuth 사용량 + 구독."""
from . import base

AUTH_PATH = "~/.codex/auth.json"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
SUBS_URL = "https://chatgpt.com/backend-api/subscriptions"
UA = "codex_cli_rs/0.55.0 (Mac OS 26.6.0; arm64)"


def _tokens():
    auth = base.read_json(AUTH_PATH)
    t = auth.get("tokens", {})
    tok, acct = t.get("access_token"), t.get("account_id")
    exp = base.jwt_exp(tok) if tok else None
    if tok and exp and exp > base.now() + 60:
        return tok, acct

    cached = base.load_cache("codex_token")
    if cached and cached.get("access_token"):
        exp = base.jwt_exp(cached["access_token"])
        if exp and exp > base.now() + 60:
            return cached["access_token"], cached.get("account_id", acct)

    refresh = t.get("refresh_token") or (cached or {}).get("refresh_token")
    if not refresh:
        raise base.CollectError("토큰 없음")
    data = base.http_post(TOKEN_URL, form={
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": CLIENT_ID,
    })
    tok = data["access_token"]
    entry = {"access_token": tok,
             "refresh_token": data.get("refresh_token", refresh),
             "account_id": acct}
    if data.get("id_token"):
        entry["id_token"] = data["id_token"]
    base.save_cache("codex_token", entry)
    return tok, acct


def _window_label(seconds):
    if seconds in (18000, 14400):
        return "5시간" if seconds == 18000 else "4시간"
    if seconds == 86400:
        return "1일"
    if seconds == 604800:
        return "7일"
    if seconds and seconds % 3600 == 0:
        return f"{seconds // 3600}시간"
    if seconds and seconds % 86400 == 0:
        return f"{seconds // 86400}일"
    return "창"


def collect():
    tok, acct = _tokens()
    h = {"Authorization": f"Bearer {tok}", "ChatGPT-Account-Id": acct,
         "User-Agent": UA, "Accept": "application/json"}
    usage, stale = base.cached_fetch(
        "codex_usage", lambda: base.http_get(USAGE_URL, h))

    windows = []
    rl = usage.get("rate_limit") or {}
    pw = rl.get("primary_window")
    if pw:
        windows.append(base.win(
            "primary", _window_label(pw.get("limit_window_seconds")),
            pw.get("used_percent", 0), pw.get("reset_at")))
    sw = rl.get("secondary_window")
    if sw:
        windows.append(base.win(
            "secondary", _window_label(sw.get("limit_window_seconds")),
            sw.get("used_percent", 0), sw.get("reset_at")))
    for extra in usage.get("additional_rate_limits") or []:
        name = extra.get("limit_name", "기타").replace("GPT-5.3-", "").replace("GPT-", "")
        erl = extra.get("rate_limit") or {}
        for wkey, wname in (("primary_window", "5시간"), ("secondary_window", "7일")):
            w = erl.get(wkey)
            if w:
                windows.append(base.win(
                    f"{name}-{wkey}", f"{name} {_window_label(w.get('limit_window_seconds')) or wname}",
                    w.get("used_percent", 0), w.get("reset_at")))

    billing = None
    try:
        subs = base.http_get(f"{SUBS_URL}?account_id={acct}", h)
        until = subs.get("active_until")
        if until:
            billing = {"cycle": subs.get("billing_period"),
                       "next_date": until[:10],
                       "label": "다음 결제일" if subs.get("will_renew") else "만료일"}
    except base.CollectError:
        pass

    credits = usage.get("credits") or {}
    if credits.get("has_credits") and not credits.get("unlimited"):
        bal = credits.get("balance")
        windows.append(base.win("credits", "크레딧", 0, None, f"잔액 ${bal}"))

    plan = (usage.get("plan_type") or "").replace("pro", "Pro").replace("plus", "Plus") or None
    return base.provider("codex", "Codex", plan=plan,
                         account=usage.get("email"), windows=windows, billing=billing,
                         stale_age=stale)
