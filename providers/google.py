"""Google (Gemini CLI / Antigravity) — Code Assist 쿼터.

개인 계정은 라이선스가 없으면 retrieveUserQuota가 403을 반환한다.
그 경우 에러 카드로 표시한다.

OAuth 클라이언트는 소스에 포함하지 않는다 — config.json의
`google_oauth_clients` 또는 GOOGLE_OAUTH_CLIENT_ID{,_2} /
GOOGLE_OAUTH_CLIENT_SECRET{,_2} 환경변수로 제공한다.
gemini-cli/antigravity가 배포하는 desktop-app 클라이언트 값을 사용하면 된다.
"""
import os
from . import base

CREDS_PATH = "~/.gemini/oauth_creds.json"
ACCOUNTS_PATH = "~/.gemini/google_accounts.json"
OCX_PATH = "~/.opencodex/auth.json"
TOKEN_URL = "https://oauth2.googleapis.com/token"
HOST = "https://daily-cloudcode-pa.googleapis.com"


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
    # opencodex antigravity 계정 우선
    try:
        reg = base.read_json(OCX_PATH)
        ga = reg.get("google-antigravity") or {}
        acct_id = ga.get("activeAccountId")
        for a in ga.get("accounts") or []:
            if a.get("id") == acct_id:
                cred = a.get("credential") or {}
                if cred.get("access") and cred.get("expires", 0) / 1000 > base.now() + 60:
                    return cred["access"], cred.get("projectId"), cred.get("email")
                if cred.get("refresh"):
                    return _refresh(cred["refresh"], 1), cred.get("projectId"), cred.get("email")
    except base.CollectError:
        pass

    # gemini-cli 자격증명
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
    h = {"Authorization": f"Bearer {tok}"}
    try:
        q = base.http_post(f"{HOST}/v1internal:retrieveUserQuota", h,
                           {"project": project or ""})
    except base.CollectError as e:
        return base.err_provider(
            "google", "Gemini / Antigravity", account=email,
            error="개인 쿼터 미지원 계정" if "40" in str(e) else str(e))

    windows = []
    for b in q.get("buckets") or []:
        name = b.get("modelId") or b.get("tokenType") or "쿼터"
        rem = b.get("remainingFraction")
        if rem is not None:
            windows.append(base.win(
                name, name, (1 - rem) * 100,
                base.iso_to_epoch(b.get("resetTime"))))
    return base.provider("google", "Gemini / Antigravity",
                         account=email, windows=windows)
