"""날씨(wttr.in) + AI 뉴스 수집.

뉴스 소스:
- x.com 검색 — ego lite 브라우저의 로그인 세션으로 스크레이핑 (ego-browser nodejs)
- threads.com — AI 공식 계정 프로필 스크레이핑 (동일 세션)
- Google News RSS — 한국어 AI 뉴스 (ego 실패 시에도 동작하는 폴백)
"""
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from providers import base

EGO_BIN = shutil.which("ego-browser") or os.path.expanduser("~/.local/bin/ego-browser")
NEWS_TTL = 900        # 뉴스 스크레이프 간격 — 브라우저 동작이라 무겁다
WEATHER_TTL = 1800
GNEWS_TTL = 1800

# --- ego 브라우저 스크립트 (x.com 검색 + threads 프로필) ---

_X_EXTRACT = r'''
(() => {
  const arts = [...document.querySelectorAll('article[data-testid="tweet"]')];
  const items = arts.map((a) => {
    const linkEl = [...a.querySelectorAll('a[href*="/status/"]')]
      .map((x) => x.getAttribute('href') || '')
      .find((h) => /^\/[^/]+\/status\/\d+$/.test(h));
    if (!linkEl) return null;
    const [, handle, , id] = linkEl.split('/');
    const textEl = a.querySelector('[data-testid="tweetText"]');
    const time = a.querySelector('time');
    return { id, handle, text: textEl ? textEl.innerText : '',
             url: 'https://x.com' + linkEl,
             ts: time ? time.getAttribute('datetime') : null };
  }).filter(Boolean);
  return JSON.stringify({ items });
})()'''

_TH_EXTRACT = r'''
(() => {
  const seen = new Set(); const items = [];
  for (const a of document.querySelectorAll('a[href*="/post/"]')) {
    const href = a.getAttribute('href') || '';
    const m = /^\/@([^/]+)\/post\/([A-Za-z0-9_-]+)/.exec(href);
    if (!m || seen.has(m[2])) continue;
    seen.add(m[2]);
    let cont = a;
    for (let i = 0; i < 10 && cont; i++) {
      cont = cont.parentElement;
      if (cont && cont.querySelector('time') && (cont.innerText || '').length > 60) break;
    }
    if (!cont) continue;
    const time = cont.querySelector('time');
    const lines = (cont.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
    let body = '';
    for (let i = 0; i < lines.length; i++) {
      if (/^\d+(초|분|시간|일|주)/.test(lines[i])) { body = lines.slice(i + 1).join(' '); break; }
    }
    if (!body) body = lines.slice(2).join(' ');
    items.push({ author: m[1], text: body.slice(0, 200),
                 url: 'https://www.threads.com' + href,
                 ts: time ? time.getAttribute('datetime') : null });
    if (items.length >= 6) break;
  }
  return JSON.stringify({ items });
})()'''


def _ego_script(x_query, th_accounts):
    x_url = "https://x.com/search?q=" + re.sub(r"\s", "%20", x_query) + "&src=typed_query"
    return f"""
const space = await useOrCreateTaskSpace('modelused-news');
const out = {{ x: [], th: [], err: [] }};
try {{
  await openOrReuseTab({json.dumps(x_url)}, {{ wait: true, timeout: 25 }});
  await wait(3);
  for (let i = 0; i < 3; i++) {{
    const b = JSON.parse(await js({json.dumps(_X_EXTRACT)}));
    for (const t of b.items) if (!out.x.find(v => v.id === t.id)) out.x.push(t);
    await scrollBy(1600); await wait(1.5);
  }}
}} catch (e) {{ out.err.push('x:' + String(e).slice(0, 80)); }}
for (const acct of {json.dumps(th_accounts)}) {{
  try {{
    await openOrReuseTab('https://www.threads.com/@' + acct, {{ wait: true, timeout: 20 }});
    await wait(3);
    const b = JSON.parse(await js({json.dumps(_TH_EXTRACT)}));
    for (const t of b.items) out.th.push(t);
  }} catch (e) {{ out.err.push('th:' + acct + ':' + String(e).slice(0, 60)); }}
}}
cliLog('MU_NEWS:' + JSON.stringify(out));
await completeTaskSpace(space.id, {{ keep: false }});
"""


def _clean_text(t):
    t = re.sub(r"\s+", " ", (t or "")).strip()
    t = re.sub(r"\s*번역하기.*$", "", t)          # Threads 번역 버튼 꼬리
    t = re.sub(r"(\s+\d+){2,5}$", "", t)         # 반응 카운트 꼬리
    return t[:200]


def _ego_news(query, th_accounts):
    """ego lite 세션으로 X 검색 + Threads 프로필을 긁어 뉴스 아이템으로 정규화."""
    try:
        proc = subprocess.run(
            [EGO_BIN, "nodejs"], input=_ego_script(query, th_accounts).encode(),
            capture_output=True, timeout=150)
    except Exception:
        return []
    # cliLog 출력은 환경에 따라 stdout 또는 stderr로 나온다 — 둘 다 스캔
    s = proc.stdout.decode("utf-8", "replace") + "\n" + proc.stderr.decode("utf-8", "replace")
    m = re.search(r"MU_NEWS:(\{.*\})", s)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except Exception:
        return []
    items = []
    for t in data.get("x", []):
        text = _clean_text(t.get("text"))
        if not text:
            continue
        items.append({"title": text, "source": "𝕏 @" + (t.get("handle") or ""),
                      "url": t.get("url") or "", "group": "social",
                      "ts": base.iso_to_epoch(t.get("ts"))})
    for t in data.get("th", []):
        text = _clean_text(t.get("text"))
        if not text:
            continue
        items.append({"title": text, "source": "Threads @" + (t.get("author") or ""),
                      "url": t.get("url") or "", "group": "social",
                      "ts": base.iso_to_epoch(t.get("ts"))})
    return items


def _google_news():
    def fetch():
        raw = base.http_get_raw(
            "https://news.google.com/rss/search"
            "?q=AI%20OR%20%EC%9D%B8%EA%B3%B5%EC%A7%80%EB%8A%A5%20when:1d"
            "&hl=ko&gl=KR&ceid=KR:ko")
        root = ET.fromstring(raw)
        items = []
        for it in root.findall(".//item")[:15]:
            title = it.findtext("title") or ""
            pub = it.findtext("pubDate")
            ts = None
            if pub:
                try:
                    ts = parsedate_to_datetime(pub).timestamp()
                except Exception:
                    pass
            items.append({"title": title, "source": "뉴스", "group": "news",
                          "url": it.findtext("link") or "", "ts": ts})
        return items
    try:
        data, _ = base.cached_fetch("gnews", fetch, ttl=GNEWS_TTL)
        return data
    except base.CollectError:
        return []


def fetch_weather():
    def fetch():
        d = base.http_get("https://wttr.in/?format=j1&lang=ko")
        c = d["current_condition"][0]
        desc = (c.get("lang_ko") or [{}])[0].get("value") \
            or (c.get("weatherDesc") or [{}])[0].get("value") or ""
        return {"temp_c": c.get("temp_C"), "code": str(c.get("weatherCode", "")),
                "desc": desc,
                "loc": (d.get("nearest_area") or [{}])[0]
                       .get("areaName", [{}])[0].get("value", "")}
    try:
        data, _ = base.cached_fetch("weather", fetch, ttl=WEATHER_TTL)
        return data
    except base.CollectError:
        return None


def _ego_items_cached(query, th_accounts):
    """ego 스크레이프 결과를 별도 캐시 — 실패 시 다음 갱신 주기에 재시도."""
    def fetch():
        items = _ego_news(query, th_accounts)
        if not items:
            raise base.CollectError("ego 뉴스 없음")
        return items
    try:
        data, _ = base.cached_fetch("news_ego", fetch, ttl=NEWS_TTL, backoff_429=300)
        return data
    except base.CollectError:
        return []


def _scrape_all(query, th_accounts):
    items = _ego_items_cached(query, th_accounts) + _google_news()
    # 제목 기준 중복 제거
    seen = set()
    uniq = []
    for it in items:
        k = re.sub(r"\W", "", it["title"].lower())[:60]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)
    if not uniq:
        return []
    # 최신 항목을 속보로 상단 고정, 나머지는 소셜/뉴스 인터리브로 균형 노출
    latest = max(uniq, key=lambda x: x.get("ts") or 0)
    latest["breaking"] = True
    rest = [i for i in uniq if i is not latest]
    social = sorted(
        (i for i in rest if i["source"].startswith(("𝕏", "Threads"))),
        key=lambda x: x.get("ts") or 0, reverse=True)
    press = sorted(
        (i for i in rest if not i["source"].startswith(("𝕏", "Threads"))),
        key=lambda x: x.get("ts") or 0, reverse=True)
    top = [latest]
    while len(top) < 14 and (social or press):
        for pool in (social, press):
            if pool:
                top.append(pool.pop(0))
            if len(top) >= 14:
                break
    return top


def collect_extras(cfg):
    """반환: {"weather": {...}|None, "news": [...]}."""
    query = cfg.get("x_query") or \
        "(AI OR OpenAI OR Anthropic OR Claude OR Gemini OR LLM) min_faves:50"
    th_accounts = cfg.get("threads_accounts") or ["openai", "google"]
    return {"weather": fetch_weather(), "news": _scrape_all(query, th_accounts)}
