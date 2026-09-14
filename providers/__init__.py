from . import claude, codex, grok, devin, cursor, zai, minimax, openrouter, google

REGISTRY = {
    "claude": claude,
    "codex": codex,
    "grok": grok,
    "devin": devin,
    "cursor": cursor,
    "zai": zai,
    "minimax": minimax,
    "openrouter": openrouter,
    "google": google,
}
