#!/usr/bin/env python3
"""ModelUsed 수집기 — 등록된 AI 서비스 사용량을 JSON으로 출력."""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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


def main():
    cfg = load_config()
    enabled = [p for p in cfg["providers"] if p in REGISTRY]
    with ThreadPoolExecutor(max_workers=len(enabled) or 1) as ex:
        results = list(ex.map(run_one, enabled))
    import news
    extras = news.collect_extras(cfg)
    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_epoch": time.time(),
        "providers": results,
        "weather": extras["weather"],
        "news": extras["news"],
        "page_seconds": cfg.get("page_seconds", 8),
    }
    json.dump(out, sys.stdout, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
