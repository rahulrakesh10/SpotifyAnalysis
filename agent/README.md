# Song analytics agent

A ClickHouse database holding the enriched songs, plus a read-only tool server so an AI agent can query it and write reports on demand. The plan is to chat with the agent through LibreChat.

## Status

- [x] ClickHouse with the `spotify.songs` table (730 songs, typed columns)
- [x] Read-only database login for the agent (`agent_ro`: SELECT on `spotify` only)
- [x] ClickHouse tool server (MCP) with token auth
- [x] LibreChat connected to the tool server (3 tools visible, token auth working)
- [x] Agent instructions ("Song Analyst" preset in `librechat-config/librechat.yaml`)
- [x] Charts: the agent can draw a bar chart in the chat for comparisons and rankings (LibreChat Artifacts)
- [ ] Try the agent in the chat with an Anthropic API key and tune the instructions (charts untested)
- [x] Model results loaded as tables (`model_effects`, `model_comparison`, plus `vs_expected_pct` on each song)

## Run

```bash
./setup.sh                       # once: creates .env with random passwords (not committed)
docker compose up -d --build     # starts ClickHouse and the tool server
```

Needs Docker. Data loads from `../data/spotify_2025_enriched.csv` the first time ClickHouse starts. To reload after changing the CSV, run `docker compose down -v` and start again.

## Chat with the agent (LibreChat)

```bash
./setup-librechat.sh    # clones LibreChat, writes its config, starts it
```

Open http://localhost:3080, create an account, and add your Anthropic API key when asked (it stays in your own account in LibreChat, not in any file). Pick **Song Analyst** in the model menu.

## What the agent can do

The tool server gives the agent three tools: `list_databases`, `list_tables` and `run_query`. It runs through the `agent_ro` login, which cannot write, alter or drop anything.

- ClickHouse: http://127.0.0.1:8123
- Tool server: http://127.0.0.1:8000/mcp (needs `MCP_AUTH_TOKEN` from `.env` as a bearer token)

Both ports are only reachable from your own computer.

## Tables

- `songs`: one row per song (730), including `vs_expected_pct` (growth vs what's typical for its age; blank for 23 songs)
- `model_effects`: each factor's effect on growth, its range, and whether it holds up after adjustment
- `model_comparison`: how well each model predicts, including on artists it hasn't seen

## Testing

`python3 query.py "SELECT count() FROM spotify.songs"` runs SQL through the tool server the same way the agent does. See `example-questions.md` for checked questions.

## Start and stop

`./start.sh` starts everything (and Docker if needed). `./stop.sh` shuts it down; your data is kept.
