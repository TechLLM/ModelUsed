"""Google (Antigravity / Gemini) — Code Assist QuotaSummary.

cloudcode-pa는 인식된 클라이언트 UA 없이 호출하면 403을 반환한다 —
agy 바이너리처럼 User-Agent: antigravity를 보낸다.

토큰 우선순위:
1. ~/.opencodex/auth.json의 google-antigravity 계정 (refresh로 갱신)
2. ~/.gemini/antigravity-cli/antigravity-oauth-token
3. ~/.gemini/oauth_creds.json (gemini-cli — 개인 무료 tier는
   UNSUPPORTED_CLIENT로 쿼터 미지원일 수 있음)

OAuth 클라이언트는 소스에 포함하지 않는다 — config.json의
`google_oauth_clients` 또는 GOOGLE_OAUTH_CLIENT_ID{,_2} /
GOOGLE_OAUTH_CLIENT_SECRET{,_2} 환경변수로 제공한다.
gemini-cli/antigravity가 배포하는 desktop-app 클라이언트 값을 사용하면 된다.
"""
import os
from . import base

CREDS_PATH = "~/.gemini/oauth_creds.json"
ACCOUNTS_PATH = "~/.gemini/google_accounts.json"
AGY_TOKEN_PATH = "~/.gemini/antigravity-cli/antigravity-oauth-token"
OCX_PATH = "~/.opencodex/auth.json"
TOKEN_URL = "https://oauth2.googleapis.com/token"
HOST = "https://cloudcode-pa.googleapis.com"
UA = "antigravity"


def _clients():
    try:
        cfg = base.read_json(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config.json"))
        cls = [(c["id"], c["secret"])
               for c in cfg.get("google_oauth_clients") or []
               if c.get("id") and c.get("secret")]
        if cls:
            return cls
    except Exception:
        pass
    env = []
    for sfx in ("", "_2"):
        cid = os.environ.get(f"GOOGLE_OAUTH_CLIENT_ID{sfx}")
        sec = os.environ.get(f"GOOGLE_OAUTH_CLIENT_SECRET{sfx}")
        if cid and sec:
            env.append((cid, sec))
    return env


def _refresh(refresh_token, client_idx):
    clients = _clients()
    if client_idx >= len(clients):
        raise base.CollectError("google_oauth_clients 미설정 — config.json 참조")
    cid, secret = clients[client_idx]
    data = base.http_post(TOKEN_URL, form={
        "client_id": cid, "client_secret": secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token"})
    return data["access_token"]


def _token():
    """반환: (access_token, project_id|None, email|None)."""
    # 1. opencodex antigravity 계정 — refresh 가능
    try:
        reg = base.read_json(OCX_PATH)
        ga = reg.get("google-antigravity") or {}
        acct_id = ga.get("activeAccountId")
        for a in ga.get("accounts") or []:
            if a.get("id") == acct_id:
                cred = a.get("credential") or {}
                email = cred.get("email") or a.get("email")
                if cred.get("access") and cred.get("expires", 0) / 1000 > base.now() + 60:
                    return cred["access"], cred.get("projectId"), email
                if cred.get("refresh"):
                    try:
                        tok = _refresh(cred["refresh"], 1)
                        cred["access"] = tok
                        cred["expires"] = int(base.now() * 1000) + 3500 * 1000
                        base.write_json(OCX_PATH, reg)
                        return tok, cred.get("projectId"), email
                    except base.CollectError:
                        pass
    except (base.CollectError, Exception):
        pass

    # 2. antigravity-cli 단독 토큰 파일
    try:
        tok = open(os.path.expanduser(AGY_TOKEN_PATH)).read().strip()
        if tok:
            return tok, None, None
    except Exception:
        pass

    # 3. gemini-cli 자격증명 — refresh 후 조회 (개인 무료 tier는 403일 수 있음)
    c = base.read_json(CREDS_PATH)
    if c.get("access_token") and c.get("expiry_date", 0) / 1000 > base.now() + 60:
        tok = c["access_token"]
    elif c.get("refresh_token"):
        tok = _refresh(c["refresh_token"], 0)
        c["access_token"] = tok
        c["expiry_date"] = int(base.now() * 1000) + 3500 * 1000
        base.write_json(CREDS_PATH, c)
    else:
        raise base.CollectError("토큰 없음")
    email = None
    try:
        email = base.read_json(ACCOUNTS_PATH).get("active")
    except Exception:
        pass
    return tok, None, email


def collect():
    tok, project, email = _token()
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
         "User-Agent": UA}
    body = {"project": project} if project else {}
    try:
        q, stale = base.cached_fetch(
            "google_quota", lambda: base.http_post(
                f"{HOST}/v1internal:retrieveUserQuotaSummary", data=body,
                headers=h))
    except base.CollectError as e:
        return base.err_provider(
            "google", "Gemini / Antigravity", account=email,
            error="개인 쿼터 미지원 계정" if "40" in str(e) else str(e))

    windows = []
    latest_reset = None
    for g in q.get("groups") or []:
        gname = g.get("displayName") or "모델"
        gname = {"Gemini Models": "Gemini",
                 "Claude and GPT models": "Claude·GPT"}.get(gname, gname)
        for b in g.get("buckets") or []:
            frac = b.get("remainingFraction")
            if frac is None:
                continue
            wname = b.get("window") or "period"
            wlabel = {"weekly": "주간", "5h": "5시간"}.get(wname, wname)
            rt = base.iso_to_epoch(b.get("resetTime"))
            if rt and (latest_reset is None or rt > latest_reset):
                latest_reset = rt
            windows.append(base.win(
                f"{wname}-{gname}", f"{gname} {wlabel}",
                (1 - frac) * 100, rt))

    # legacy flat buckets (그룹 없는 응답 호환)
    if not windows:
        for b in q.get("buckets") or []:
            frac = b.get("remainingFraction")
            if frac is None:
                continue
            name = b.get("modelId") or b.get("tokenType") or "쿼터"
            windows.append(base.win(
                name, name, (1 - frac) * 100,
                base.iso_to_epoch(b.get("resetTime"))))

    billing = None
    if latest_reset:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(latest_reset, timezone.utc)
        billing = {"cycle": "weekly", "next_date": dt.date().isoformat(),
                   "label": "주간 리셋"}
    return base.provider("google", "Gemini / Antigravity",
                         account=email, windows=windows, billing=billing,
                         stale_age=stale)
