"""Cursor — opencodex 계정 레지스트리의 세션 JWT로 Connect-RPC 사용량 조회."""
from . import base

AUTH_PATH = "~/.opencodex/auth.json"
RPC = "https://api2.cursor.sh/aiserver.v1.DashboardService"


def _token():
    reg = base.read_json(AUTH_PATH)
    cur = reg.get("cursor") or {}
    acct_id = cur.get("activeAccountId")
    for a in cur.get("accounts") or []:
        if a.get("id") == acct_id:
            cred = a.get("credential") or {}
            tok = cred.get("access")
            exp = cred.get("expires")  # ms
            if tok and exp and exp / 1000 > base.now() + 60:
                return tok
            if tok:
                raise base.CollectError("세션 만료 — Cursor 재로그인 필요")
    raise base.CollectError("계정 없음")


def collect():
    tok = _token()
    h = {"Authorization": f"Bearer {tok}", "Connect-Protocol-Version": "1"}
    d, stale = base.cached_fetch("cursor_usage", lambda: base.http_post(
        f"{RPC}/GetCurrentPeriodUsage", headers=h))
    pu = d.get("planUsage") or {}

    windows = []
    end_ms = int(d.get("billingCycleEnd") or 0)
    if pu.get("totalPercentUsed") is not None:
        inc = (pu.get("includedSpend") or 0) / 100
        spent = (pu.get("totalSpend") or 0) / 100
        windows.append(base.win(
            "period", "청구 주기", pu["totalPercentUsed"],
            end_ms / 1000 or None,
            f"${spent:.2f} 사용 (포함 ${inc:.0f})"))
    for key, label in (("autoPercentUsed", "Auto 모델"), ("apiPercentUsed", "API")):
        if pu.get(key) is not None:
            windows.append(base.win(key, label, pu[key]))

    billing = None
    if end_ms:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(end_ms / 1000, timezone.utc)
        billing = {"cycle": "monthly", "next_date": dt.date().isoformat(),
                   "label": "청구 주기 종료"}
    return base.provider("cursor", "Cursor", plan="Pro",
                         windows=windows, billing=billing, stale_age=stale)
