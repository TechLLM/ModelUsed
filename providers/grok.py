"""Grok (xAI Grok Build) — cli-chat-proxy billing API.

~/.grok/auth.json의 OIDC 세션 토큰(key)으로 두 엔드포인트를 호출한다:
- GET /v1/billing           — 월간 $ 한도/사용량, 청구 주기
- GET /v1/billing?format=credits — 주간 통합 사용 풀 + 제품별 breakdown

토큰이 만료돼 있으면 `grok models`를 한 번 실행해 auth.x.ai 갱신을 유도한다
(auth.x.ai는 Cloudflare 봇 차단으로 외부 refresh가 안 된다).
"""
import json
import subprocess
from . import base

AUTH_PATH = "~/.grok/auth.json"
VERSION_PATH = "~/.grok/version.json"
BASE = "https://cli-chat-proxy.grok.com"
CLIENT_SURFACE = "grok-build"


def _entries():
    d = base.read_json(AUTH_PATH)
    if not d:
        raise base.CollectError("auth.json 없음")
    out = []
    for acct, e in d.items():
        if (e or {}).get("key"):
            out.append(e)
    if not out:
        raise base.CollectError("세션 토큰 없음")
    return out


def _token(refreshed=False):
    """만료 안 된 최신 토큰. 전부 만료면 grok models로 갱신 유도 후 재시도."""
    now = base.now()
    entries = _entries()

    def fresh(e):
        exp = base.iso_to_epoch(e.get("expires_at"))
        return exp and exp > now + 60

    live = [e for e in entries if fresh(e)]
    if live:
        live.sort(key=lambda e: base.iso_to_epoch(e.get("expires_at")) or 0,
                  reverse=True)
        return live[0]["key"], live[0].get("email")

    if refreshed:
        # 갱신 후에도 만료 상태 → 최신 것을 반환해 API 에러를 보여준다
        entries.sort(key=lambda e: e.get("create_time") or "", reverse=True)
        return entries[0]["key"], entries[0].get("email")

    # grok CLI가 auth.x.ai로 직접 갱신한다 (외부 refresh는 Cloudflare 차단)
    try:
        subprocess.run(["grok", "models"], capture_output=True, timeout=30)
    except Exception:
        pass
    return _token(refreshed=True)


def _version():
    try:
        v = base.read_json(VERSION_PATH).get("version")
        if v:
            return str(v)
    except Exception:
        pass
    try:
        out = subprocess.check_output(["grok", "--version"], timeout=10,
                                      stderr=subprocess.DEVNULL).decode()
        for tok in out.split():
            if tok[0].isdigit() and "." in tok:
                return tok
    except Exception:
        pass
    return "1.0.30"


def _headers(tok):
    return {"Authorization": f"Bearer {tok}", "Accept": "application/json",
            "x-grok-client-version": _version(),
            "x-grok-client-surface": CLIENT_SURFACE}


def _val(v):
    """{"val": 68} 형태 → 숫자. USD cents."""
    if isinstance(v, dict):
        v = v.get("val")
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def collect():
    tok, email = _token()
    h = _headers(tok)

    monthly, _ = base.cached_fetch(
        "grok_billing", lambda: base.http_get(f"{BASE}/v1/billing", h))
    credits, stale = base.cached_fetch(
        "grok_credits", lambda: base.http_get(
            f"{BASE}/v1/billing?format=credits", h))

    mcfg = (monthly or {}).get("config") or {}
    ccfg = (credits or {}).get("config") or {}

    windows = []

    # 주간 통합 사용 풀 (Chat/Build/API 공유)
    period = ccfg.get("currentPeriod") or {}
    end = base.iso_to_epoch(period.get("end") or ccfg.get("billingPeriodEnd"))
    pct = ccfg.get("creditUsagePercent")
    if pct is not None:
        windows.append(base.win("weekly", "주간 통합", pct, end))

    # 제품별 breakdown
    for p in ccfg.get("productUsage") or []:
        name = p.get("product") or "product"
        short = {"GrokBuild": "Build", "Api": "API", "GrokChat": "Chat",
                 "Imagine": "Imagine", "Voice": "Voice"}.get(name, name)
        if p.get("usagePercent") is not None:
            windows.append(base.win(
                f"weekly-{name}", f"주간 {short}", p["usagePercent"], end))

    # 월간 $ 한도
    limit = _val(mcfg.get("monthlyLimit"))
    used = _val(mcfg.get("used"))
    m_end = base.iso_to_epoch(mcfg.get("billingPeriodEnd"))
    if limit > 0:
        windows.append(base.win("monthly", "월간", used / limit * 100, m_end,
                                f"${used / 100:.2f} / ${limit / 100:.0f}"))
    elif used > 0:
        windows.append(base.win("monthly", "월간", None, m_end,
                                f"${used / 100:.2f} 사용"))

    billing = None
    if m_end:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(m_end, timezone.utc)
        billing = {"cycle": "monthly", "next_date": dt.date().isoformat(),
                   "label": "청구 주기 종료"}

    return base.provider("grok", "Grok", plan="Build", account=email,
                         windows=windows, billing=billing, stale_age=stale)
