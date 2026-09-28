# Project Rules

## LLM usage

If any AI/LLM capability is ever needed in this project, it MUST use
**MiniMax-M3** or **MiniMax-M3.1** only (the owner's MiniMax Coding Plan).
Never call Claude, GPT, Gemini, Grok, or any other model for inference
inside this widget.

## GitHub

- Repository: `TechLLM/ModelUsed` (public, MIT).
- NEVER push as `Mayouly-AI` — the shared keychain may hold that account's
  credential. Always push as `TechLLM` explicitly:

  ```bash
  git push "https://x-access-token:$(gh auth token --user TechLLM)@github.com/TechLLM/ModelUsed.git" HEAD:master
  ```

- Commit author/committer must be `TechLLM <TechLLM@users.noreply.github.com>`.

## Build & run

- `./build.sh` → `./install.sh` (installs to `~/Applications`, registers a
  LaunchAgent, relaunches).
- Never run `open` after `install.sh` — it already launches the app, and a
  second `open` spawns a duplicate widget.

## Secrets

- `config.json` is local-only (gitignored). Never commit real tokens,
  OAuth client secrets, account emails, or absolute user paths.
- `config.example.json` is the public template.

## Collector

- Usage track: `python3 collect.py --usage` (~1-2s, app polls every 30s).
- Extras track: `python3 collect.py --extras` (weather + ego-browser
  scraping, ~30s, app polls every 5min).
- Keep the two tracks separate — slow scraping must never block usage data.
