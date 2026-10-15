# Song analytics agent

A ClickHouse database holding the enriched songs, plus a read-only tool server so an AI agent can query it and write reports on demand. The plan is to chat with the agent through LibreChat.

## Status

- [x] ClickHouse with the `spotify.songs` table (730 songs, typed columns)
- [x] Read-only database login for the agent (`agent_ro`: SELECT on `spotify` only)
- [x] ClickHouse tool server (MCP) with token auth
- [x] LibreChat connected to the tool server (3 tools visible, token auth working)
- [x] Agent instructions ("Song Analyst" preset in `librechat-config/librechat.yaml`)
- [x] Agent runs on a local Ollama model (`song-analyst`, made from llama3.2), so no API key is needed
- [x] LibreChat reaches Ollama and gets proper tool calls back (checked from inside the container)
- [ ] Try the agent in the chat and check its answers against the database (not done yet)
- [ ] Charts: switched off for the small local model; rules saved in `librechat-config/charts-addendum.md`
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

Open http://localhost:3080, create an account (it stays on your computer), and pick **Song Analyst** in the model menu. No API key is needed: it uses the local model through Ollama, so Ollama must be running. `./start.sh` creates the `song-analyst` model from your existing `llama3.2` the first time.

The model is small, so check its numbers. In testing, a 14B model (`qwen2.5-coder`) ignored the database and made up results, while `llama3.2` called the tool and answered correctly. Every answer includes the SQL it ran, so it can be checked, and `try_agent.py` runs the same agent from the terminal.

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

`python3 checks.py` runs a 12-point smoke test (data matches the CSVs, model results are as reported, the agent's login is read-only). Run it after `./start.sh` and after any change to the database setup.

`python3 query.py "SELECT count() FROM spotify.songs"` runs SQL through the tool server the same way the agent does. See `example-questions.md` for checked questions.

## Start and stop

`./start.sh` starts everything (and Docker if needed). `./stop.sh` shuts it down; your data is kept.
