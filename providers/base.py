"""공통 헬퍼: HTTP, 키체인, JWT, 토큰 캐시."""
import base64
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request

HOME = os.path.expanduser("~")
CACHE_DIR = os.path.join(HOME, ".cache", "modelused")
os.makedirs(CACHE_DIR, exist_ok=True)


class CollectError(Exception):
    pass


def http_get(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise CollectError(f"HTTP {e.code}") from e
    except Exception as e:
        raise CollectError(str(e)[:120]) from e


def http_get_raw(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode()
    except urllib.error.HTTPError as e:
        raise CollectError(f"HTTP {e.code}") from e
    except Exception as e:
        raise CollectError(str(e)[:120]) from e


def http_post(url, data=None, form=None, headers=None, timeout=15):
    h = dict(headers or {})
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    else:
        body = json.dumps(data or {}).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise CollectError(f"HTTP {e.code}") from e
    except Exception as e:
        raise CollectError(str(e)[:120]) from e


def http_post_curl(url, data=None, headers=None, timeout=15):
    """curl 기반 POST — Cloudflare 봇 차단 엔드포인트용 폴백."""
    cmd = ["/usr/bin/curl", "-sS", "-m", str(timeout), "-X", "POST", url,
           "-H", "Content-Type: application/json"]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    cmd += ["-d", json.dumps(data or {})]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=timeout + 5)
        return json.loads(out.decode())
    except subprocess.CalledProcessError as e:
        raise CollectError(f"curl 실패({e.returncode})") from e
    except json.JSONDecodeError as e:
        raise CollectError("curl 응답 파싱 실패") from e


def keychain_password(service):
    try:
        out = subprocess.check_output(
            ["security", "find-generic-password", "-s", service, "-w"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except subprocess.CalledProcessError:
        raise CollectError("keychain item 없음")


def read_json(path):
    with open(os.path.expanduser(path)) as f:
        return json.load(f)


def write_json(path, obj):
    path = os.path.expanduser(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def cache_path(name):
    return os.path.join(CACHE_DIR, name + ".json")


def load_cache(name):
    try:
        return read_json(cache_path(name))
    except Exception:
        return None


def save_cache(name, obj):
    write_json(cache_path(name), obj)


def jwt_exp(token):
    """JWT의 exp(epoch sec). 실패 시 None."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("exp")
    except Exception:
        return None


def iso_to_epoch(s):
    """'2026-09-13T22:00:00.392401+00:00' → epoch sec."""
    from datetime import datetime, timezone

    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def now():
    return time.time()


def cached_fetch(name, fetch, ttl=None, backoff_429=120):
    """API 응답 캐시. 반환: (data, stale_age_sec | None)

    - ttl 내 성공 캐시가 있으면 네트워크 호출 생략
    - 실패(429 등) 시 마지막 성공 응답을 반환하고 백오프 설정
    """
    meta = load_cache(name + "_meta") or {}
    data = load_cache(name)
    fetched_at = meta.get("fetched_at", 0)

    if data is not None and ttl and now() - fetched_at < ttl:
        return data, None
    if now() < meta.get("next_allowed", 0):
        if data is not None:
            return data, now() - fetched_at
        raise CollectError("API 백오프 중")

    try:
        data = fetch()
        save_cache(name, data)
        save_cache(name + "_meta", {"fetched_at": now(), "next_allowed": 0, "fails": 0})
        return data, None
    except CollectError as e:
        if "429" in str(e):
            fails = meta.get("fails", 0) + 1
            meta["fails"] = fails
            meta["next_allowed"] = now() + backoff_429 * min(fails, 4)
        else:
            meta["fails"] = 0
            meta["next_allowed"] = now() + 60
        meta["fetched_at"] = fetched_at or now()
        save_cache(name + "_meta", meta)
        if data is None:
            raise
        return data, now() - fetched_at


# --- 출력 스키마 헬퍼 ---


def win(key, label, used_pct, resets_at=None, detail=""):
    return {
        "key": key,
        "label": label,
        "used_pct": round(float(used_pct), 1) if used_pct is not None else None,
        "resets_at": resets_at,
        "detail": detail,
    }


def provider(pid, name, plan=None, account=None, windows=None, billing=None,
             status="ok", error=None, stale_age=None):
    return {
        "id": pid,
        "name": name,
        "plan": plan,
        "account": account,
        "status": status,
        "error": error,
        "windows": windows or [],
        "billing": billing,
        "stale_age": stale_age,
    }


def err_provider(pid, name, account=None, error=""):
    return provider(pid, name, account=account, status="error",
                    error=error or "사용량 조회 불가")
