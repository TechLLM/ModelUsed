"""Claude (Anthropic) — Claude Code OAuth 사용량."""
from . import base

TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
PROFILE_URL = "https://api.anthropic.com/api/oauth/profile"
BETA = "oauth-2025-04-20"


def _keychain_creds():
    raw = base.keychain_password("Claude Code-credentials")
    return raw and __import__("json").loads(raw).get("claudeAiOauth", {}) or {}


def _token():
    """키체인 유효 토큰 → 캐시 유효 토큰 → refresh 순으로 시도."""
    refresh = None
    try:
        creds = _keychain_creds()
        tok = creds.get("accessToken")
        exp = creds.get("expiresAt")  # ms
        if tok and (not exp or exp / 1000 > base.now() + 60):
            return tok
        refresh = creds.get("refreshToken")
    except base.CollectError:
        pass

    cached = base.load_cache("claude_token") or {}
    ctok = cached.get("accessToken")
    cexp = cached.get("expiresAt")
    if ctok and cexp and cexp / 1000 > base.now() + 60:
        return ctok
    refresh = refresh or cached.get("refreshToken")

    if not refresh:
        raise base.CollectError("토큰 없음")

    # refresh 재시도 백오프 — 실패 직후엔 재시도하지 않음
    meta = base.load_cache("claude_token_meta") or {}
    if base.now() < meta.get("refresh_next", 0):
        raise base.CollectError("토큰 갱신 백오프 중")

    # platform.claude.com 은 Cloudflare 봇 차단이 걸려 있어 curl 사용
    data = base.http_post_curl(TOKEN_URL, {
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": CLIENT_ID,
    })
    if "access_token" not in data:
        err = (data.get("error") or {}).get("type", "unknown")
        meta["refresh_next"] = base.now() + (1800 if "rate" in err else 120)
        base.save_cache("claude_token_meta", meta)
        raise base.CollectError(f"토큰 갱신 실패: {err}")
    meta["refresh_next"] = 0
    base.save_cache("claude_token_meta", meta)
    tok = data["access_token"]
    oauth = data
    entry = {
        "accessToken": tok,
        "refreshToken": oauth.get("refresh_token", refresh),
        "expiresAt": int(base.now() * 1000) + int(oauth.get("expires_in", 3600)) * 1000,
    }
    base.save_cache("claude_token", entry)
    return tok


def _next_monthly(day):
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date()
    y, m = today.year, today.month
    for _ in range(14):
        try:
            d = datetime(y, m, min(day, 28)).date()
        except ValueError:
            d = None
        # day-of-month에 맞는 날짜 생성 (월말 초과 시 그 월은 건너뜀)
        try:
            d = datetime(y, m, day).date()
        except ValueError:
            pass
        if d and d >= today:
            return d.isoformat()
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return None


def _stale_age(name):
    meta = base.load_cache(name + "_meta") or {}
    fetched = meta.get("fetched_at")
    return (base.now() - fetched) if fetched else None


def _build(usage, prof, stale):
    org = prof.get("organization", {})
    acct = prof.get("account", {})

    windows = []
    fh = usage.get("five_hour") or {}
    if fh:
        windows.append(base.win("5h", "5시간", fh.get("utilization", 0),
                                base.iso_to_epoch(fh.get("resets_at"))))
    sd = usage.get("seven_day") or {}
    if sd:
        windows.append(base.win("7d", "7일", sd.get("utilization", 0),
                                base.iso_to_epoch(sd.get("resets_at"))))
    for key, label in (("seven_day_opus", "Opus 주간"), ("seven_day_sonnet", "Sonnet 주간")):
        b = usage.get(key)
        if b:
            windows.append(base.win(key, label, b.get("utilization", 0),
                                    base.iso_to_epoch(b.get("resets_at"))))

    billing = None
    created = org.get("subscription_created_at")
    if created:
        day = int(created[8:10])
        nxt = _next_monthly(day)
        billing = {"cycle": "monthly", "next_date": nxt,
                   "label": f"다음 결제(추정): 매월 {day}일"}

    plan_map = {"claude_pro": "Pro", "claude_max": "Max", "claude_free": "Free"}
    plan = plan_map.get(org.get("organization_type"), org.get("organization_type"))
    return base.provider("claude", "Claude", plan=plan,
                         account=acct.get("email"), windows=windows, billing=billing,
                         stale_age=stale)


def collect():
    try:
        tok = _token()
    except base.CollectError:
        # 토큰 갱신 불가(리밋 백오프 등)여도 캐시된 사용량이 있으면 표시
        usage = base.load_cache("claude_usage")
        if not usage:
            raise
        return _build(usage, base.load_cache("claude_profile") or {},
                      _stale_age("claude_usage"))

    h = {"Authorization": f"Bearer {tok}", "anthropic-beta": BETA}
    usage, stale = base.cached_fetch(
        "claude_usage", lambda: base.http_get(USAGE_URL, h),
        ttl=600, backoff_429=900)
    try:
        prof, _ = base.cached_fetch(
            "claude_profile", lambda: base.http_get(PROFILE_URL, h),
            ttl=6 * 3600)
    except base.CollectError:
        prof = {}
    return _build(usage, prof, stale)
