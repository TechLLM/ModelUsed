"""Grok (xAI Grok Build) — 쿼터 API 미제공. 인증 상태 + 계정 정보 카드.

auth.x.ai 토큰 갱신이 Cloudflare로 차단되어, 저장된 토큰이 만료되면
grok CLI를 한 번 실행해 갱신해야 한다.
"""
import base64
import json
from . import base

AUTH_PATH = "~/.grok/auth.json"
MODELS_CACHE = "~/.grok/models_cache.json"


def _claims(jwt):
    try:
        p = jwt.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p))
    except Exception:
        return {}


def collect():
    d = base.read_json(AUTH_PATH)
    if not d:
        raise base.CollectError("auth.json 없음")
    sess = next(iter(d.values()))
    email = sess.get("email")
    exp = base.iso_to_epoch(sess.get("expires_at"))
    valid = bool(exp and exp > base.now())

    model_count = 0
    try:
        mc = base.read_json(MODELS_CACHE)
        if isinstance(mc, list):
            model_count = len(mc)
        elif isinstance(mc, dict):
            model_count = len(mc.get("models") or mc)
    except Exception:
        pass

    windows = [base.win("auth", "인증", None, None,
                        "유효" if valid else "만료 — grok 실행 시 갱신")]
    if model_count:
        windows.append(base.win("models", "사용 가능 모델", None, None,
                                f"{model_count}개"))

    if not valid:
        return base.provider("grok", "Grok", plan="Build", account=email,
                             windows=windows, status="error",
                             error="토큰 만료 — grok 한 번 실행하면 자동 갱신")
    return base.provider("grok", "Grok", plan="Build", account=email,
                         windows=windows)
