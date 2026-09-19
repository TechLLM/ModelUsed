#!/usr/bin/env python3
"""ModelUsed 수집기 — 등록된 AI 서비스 사용량을 JSON으로 출력."""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# LaunchAgent/GUI 앱 환경은 PATH가 /usr/bin:/bin 뿐 — grok, ego-browser 등
# 사용자 bin을 찾지 못해 서브프로세스 호출이 조용히 실패한다. 미리 보정한다.
for _p in (os.path.expanduser("~/.local/bin"), "/opt/homebrew/bin",
           "/usr/local/bin"):
    if _p not in os.environ.get("PATH", "").split(":"):
        os.environ["PATH"] = _p + os.pathsep + os.environ.get("PATH", "")

from providers import REGISTRY, base  # noqa: E402

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
DEFAULTS = {"providers": list(REGISTRY.keys())}


def load_config():
    try:
        cfg = base.read_json(CONFIG_PATH)
        return {**DEFAULTS, **cfg}
    except Exception:
        return DEFAULTS


def run_one(pid):
    mod = REGISTRY[pid]
    try:
        return mod.collect()
    except base.CollectError as e:
        return base.err_provider(pid, mod.__doc__.split("—")[0].strip()
                                 if mod.__doc__ else pid, error=str(e))
    except Exception as e:
        return base.err_provider(pid, pid, error=f"{type(e).__name__}: {e}")


def _stamp():
    return {"updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_epoch": time.time()}


def collect_usage(cfg):
    """프로바이더 사용량만 — 병렬 ~2초. 30초 주기로 호출된다."""
    enabled = [p for p in cfg["providers"] if p in REGISTRY]
    with ThreadPoolExecutor(max_workers=len(enabled) or 1) as ex:
        results = list(ex.map(run_one, enabled))
    return {**_stamp(), "providers": results}


def collect_extras(cfg):
    """날씨+뉴스 — ego 스크레이핑 ~20초. 5분 주기로 호출된다."""
    import news
    extras = news.collect_extras(cfg)
    return {**_stamp(), "weather": extras["weather"], "news": extras["news"],
            "page_seconds": cfg.get("page_seconds", 8)}


def main():
    cfg = load_config()
    if "--usage" in sys.argv:
        out = collect_usage(cfg)
    elif "--extras" in sys.argv:
        out = collect_extras(cfg)
    else:
        out = {**collect_usage(cfg), **collect_extras(cfg)}
    json.dump(out, sys.stdout, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
