# kidney-bot-api

FastAPI backend for the kidney-bot web dashboard: Discord OAuth login and a
settings-descriptor-driven REST API for editing per-guild bot configuration
(currently the heuristics engine). Talks to the same MongoDB database as the
bot via `utils.database` (vendored from `../../kidney-bot/utils`) — it never
connects to the bot's Discord gateway directly.

## Running

```
uv run --project services/api uvicorn app.main:app --reload --port 8000
```

Requires the same `config.json` as the bot (see `../../config.sample.json`),
plus the OAuth keys documented there (`discord_client_id`,
`discord_client_secret`, `discord_redirect_uri`, `session_secret`).
