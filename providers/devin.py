"""Devin — Codeium/Windsurf 계열 GetUserStatus로 일간/주간 쿼터 조회."""
import os
import re
from . import base

CREDS = os.path.expanduser("~/.local/share/devin/credentials.toml")
URL = "https://server.codeium.com/exa.seat_management_pb.SeatManagementService/GetUserStatus"


def _key():
    t = open(CREDS).read()
    m = re.search(r'windsurf_api_key\s*=\s*"([^"]+)"', t)
    if not m:
        raise base.CollectError("credentials.toml 없음")
    return m.group(1)


def collect():
    key = _key()
    meta = {"ideName": "windsurf", "ideVersion": "1.12.0",
            "extensionName": "windsurf", "extensionVersion": "1.12.0",
            "locale": "en", "osName": "macOS", "apiKey": key,
            "requestId": str(int(base.now()))}
    h = {"Content-Type": "application/json", "Connect-Protocol-Version": "1",
         "Authorization": f"Bearer {key}"}
    d, stale = base.cached_fetch("devin_usage", lambda: base.http_post(
        URL, data={"metadata": meta}, headers=h))
    us = d.get("userStatus") or {}
    ps = us.get("planStatus") or {}
    pi = ps.get("planInfo") or {}

    windows = []
    if ps.get("dailyQuotaRemainingPercent") is not None:
        windows.append(base.win(
            "daily", "일간", 100 - ps["dailyQuotaRemainingPercent"],
            int(ps["dailyQuotaResetAtUnix"]) if ps.get("dailyQuotaResetAtUnix") else None))
    if ps.get("weeklyQuotaRemainingPercent") is not None:
        windows.append(base.win(
            "weekly", "주간", 100 - ps["weeklyQuotaRemainingPercent"],
            int(ps["weeklyQuotaResetAtUnix"]) if ps.get("weeklyQuotaResetAtUnix") else None))
    if ps.get("availableFlexCredits") is not None:
        windows.append(base.win(
            "flex", "Flex 크레딧", None, None,
            f"{ps['availableFlexCredits']} 크레딧 남음"))

    return base.provider("devin", "Devin", plan=pi.get("planName") or "Pro",
                         account=us.get("email"), windows=windows, stale_age=stale)
