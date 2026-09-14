# ModelUsed

macOS 바탕화면 위에 항상 떠 있는 **로컬 등록 AI 서비스 사용량 위젯**.

A floating desktop widget for macOS that shows real-time usage of your
locally-registered AI services — rate-limit windows (5h / 7d / daily / weekly),
remaining credits, and next billing dates, refreshed every 60 seconds.

## 기능 / Features

- **사용량 카드** — 프로바이더별 플랜·계정·윈도우별 사용률·리셋 시각·결제일
- **AI 뉴스** — X 검색 + Threads 공식 계정 + Google News RSS, 최신 속보 상단 고정
- **날씨** — wttr.in 기반 현재 온도/상태
- **자비스 구체** — 하단에 회전하는 3D 신경망 홀로그램. 시간대와 날씨에 따라
  하늘·태양·구름·비·눈·안개·번개·별·유성 효과가 바뀐다
- 모든 프로바이더를 한 화면에 표시 (페이지 전환 없음, 필요 시 스크롤)
- 로그인 시 자동 실행 (LaunchAgent)

## 구성 / Layout

- `collect.py` — 모든 프로바이더를 병렬 수집해 JSON 출력
- `providers/` — 서비스별 수집 모듈 (`claude`, `codex`, `grok`, `devin`,
  `cursor`, `zai`, `minimax`, `openrouter`, `google`)
- `news.py` — 날씨 + AI 뉴스 수집 (ego-browser 세션 스크레이핑, Google News 폴백)
- `app/ModelUsed.swift` — borderless 플로팅 NSPanel + SwiftUI 위젯
- `config.example.json` → `config.json`으로 복사해 사용 (프로바이더 목록,
  뉴스 쿼리/Threads 계정, Google OAuth 클라이언트). `config.json`은
  gitignore 대상 — 실제 설정은 로컬에만 둔다
- `icons/` — 프로바이더 브랜드 아이콘 (macOS 스쿼클 타일 스타일)

## 빌드 / 설치

```bash
./build.sh      # ModelUsed.app 생성 (collector + 아이콘을 앱 번들에 포함)
./install.sh    # ~/Applications 에 설치 + 로그인 자동실행 등록 + 실행
```

제거:

```bash
launchctl unload ~/Library/LaunchAgents/com.modelused.widget.plist
rm ~/Library/LaunchAgents/com.modelused.widget.plist
rm -rf ~/Applications/ModelUsed.app
```

## 데이터 소스

| 서비스 | 소스 | 제공 정보 |
|---|---|---|
| Claude | macOS 키체인 OAuth → anthropic.com | 5시간/7일 사용률, 리셋 시각 |
| Codex | `~/.codex/auth.json` → chatgpt.com | 주간 + 5시간 윈도우 |
| Grok | `~/.grok/auth.json` → cli-chat-proxy.grok.com | 주간 통합 풀, 제품별 breakdown, 월간 $ |
| Devin | `~/.local/share/devin/credentials.toml` | 일간/주간 쿼터, Flex 크레딧 |
| Cursor | `~/.opencodex/auth.json` → api2.cursor.sh | 청구 주기 사용률, 종료일 |
| Z.ai | `~/.local/share/opencode/auth.json` | 5시간/주간 토큰, 월간 도구 호출 |
| MiniMax | `~/.local/share/opencode/auth.json` | 모델별 5시간/주간 잔량 |
| OpenRouter | `~/.local/share/opencode/auth.json` | 크레딧 잔액, 월간 한도 |
| Google | `~/.opencodex` / `~/.gemini` OAuth → cloudcode-pa | Gemini·Claude/GPT 주간·5시간 쿼터 |

## 보안 참고 / Security Notes

- 이 프로젝트는 **어떤 토큰·API 키도 소스에 포함하지 않는다**. 모든 자격증명은
  런타임에 로컬 파일(`~/.codex`, `~/.grok`, `~/.gemini`, `~/.opencodex`,
  `~/.local/share/opencode` 등)과 macOS 키체인에서 읽는다.
- `google.py`는 OAuth 클라이언트를 소스에 포함하지 않는다. `config.json`의
  `google_oauth_clients` 배열(`[{"id": ..., "secret": ...}]`, 첫 번째는
  gemini-cli용, 두 번째는 antigravity용) 또는 `GOOGLE_OAUTH_CLIENT_ID` /
  `GOOGLE_OAUTH_CLIENT_SECRET`(및 `_2` 접미사) 환경변수로 제공한다.
  gemini-cli/antigravity가 공식 배포하는 desktop-app 클라이언트 값을 쓰면 된다.
- 토큰 갱신 캐시는 `~/.cache/modelused/`에만 저장된다 (원본 자격증명 파일은
  건드리지 않음). 이 디렉터리는 리포에 포함되지 않는다.
- X/Threads 뉴스는 로컬 `ego-browser`의 **기존 로그인 세션**을 백그라운드로
  재사용한다 — 별도 자격증명을 저장하거나 요구하지 않는다. ego-browser가
  없으면 Google News만 표시된다.

## 확장 / Adding a provider

`providers/`에 `collect()` 함수를 가진 모듈을 추가하고 `providers/__init__.py`의
`REGISTRY`와 `config.json`에 등록하면 된다.

## License

MIT — 자유롭게 사용·수정·배포 가능.
