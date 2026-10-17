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
- [x] Ready-made song tools (`songs_mcp/`): the agent picks a tool and fills in simple options instead of writing SQL
- [x] Agent graded automatically against the database (`eval_agent.py`): 25/33 across four question sets
- [x] LibreChat connects to both tool servers (2 servers, 11 tools, no errors)
- [ ] Try the agent in the LibreChat chat window itself (needs a local account; the same route was tested with `--openai`)
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

## Song tools (what the agent actually uses)

A 3B model writes unreliable SQL, so the agent gets ready-made tools instead (`songs_mcp/server.py`), on http://127.0.0.1:8001/mcp:

| Tool | Answers |
|---|---|
| `song_stats` | song count, total streams, median growth, average length, explicit/collaboration counts, for any group |
| `top_groups` | which artist, genre or country has the most streams or songs, or the fastest growth |
| `top_songs` | the biggest or fastest-growing individual songs |
| `songs_ahead_or_behind` | songs growing faster or slower than typical for their age |
| `find_songs` | one named song or artist |
| `growth_drivers` | what predicts growth, or whether one factor matters |
| `model_fit` | how well release age predicts growth |
| `list_values` | the genres and countries that exist |

Every result starts with a plain-English `summary` sentence. Inputs are bound as parameters (a quote in a name can't break anything), genre must be a real genre, and a cleaner drops the `"null"` placeholders and made-up parameters small models send. The tools can only read. The free-form SQL server (`clickhouse`) is still configured for a stronger model; its instructions are saved in `librechat-config/sql-instructions.md`.

## Tables

- `songs`: one row per song (730), including `vs_expected_pct` (growth vs what's typical for its age; blank for 23 songs)
- `model_effects`: each factor's effect on growth, its range, and whether it holds up after adjustment
- `model_comparison`: how well each model predicts, including on artists it hasn't seen

## Testing

`python3 checks.py` runs a 12-point smoke test (data matches the CSVs, model results are as reported, the agent's login is read-only). Run it after `./start.sh` and after any change to the database setup.

`python3 query.py "SELECT count() FROM spotify.songs"` runs SQL through the tool server the same way the agent does. See `example-questions.md` for checked questions.

## Grading the agent

`python3 eval_agent.py --set dev|held|fresh|fresh2` asks the agent fixed questions and checks each answer against the real database. A question passes only if the agent actually called a tool and its answer contains the true numbers. Some are traps: requests to change data must be refused, and "does X matter" questions must not invent effects. `--model <name>` compares other local models. `--openai` sends the questions over the same interface LibreChat uses (Ollama's OpenAI-style endpoint) instead of Ollama's native one.

Last run (`llama3.2` with the tools):

| Question set | Passed | How clean the test is |
|---|---|---|
| dev (11) | 8 | tuned against |
| held (7) | 6 | failures seen earlier |
| fresh (7) | 6 | failures seen earlier |
| fresh2 (8) | 5 | cleanest: written before the last fixes |
| **All** | **25 of 33** | |

The score moves by about one question between runs, so read it as "about three in four right".

Over the route LibreChat actually uses (`--openai`), the same four sets gave 23 of 33 (fresh2 4/8, dev 7/11, held 6/7, fresh 6/7). That is the same within the run-to-run noise, so the numbers above are a fair preview of the chat window.

For comparison, the earlier version that wrote its own SQL scored about the same (9/11 and 6/7). The tools did not raise accuracy much. They removed a whole class of failure (broken SQL and quote errors) and made refusing write requests reliable: all 5 "change the data" requests were refused in the last runs.

How it got here:
- Short strict rules, a "which tool for which question" guide, and plain-English summaries in every tool result each fixed a real failure.
- A `%` in an example made the model write a broken tool call, so some question types silently produced no answer.
- Sending the text `"null"` for unused options broke every call until the cleaner dropped it (score fell to 4/11 first).
- A genre list I hard-coded as 12 of 20 was caught by `checks.py`.

**Known limits of the small model:**
- Sometimes it calls the right tool and then replies with only "Tool used: ...", with no numbers.
- Sometimes it picks the wrong tool (a list of songs when it needed totals).
- A bigger tool-capable model is the likely fix, but memory is the limit: on a 16 GB Mac with swap already nearly full (7.1 of 8 GB), the installed 14B model (about 10 GB) was not tested with the new tools because it would have made the laptop crawl. Close other apps first, or try an 8B model (about 5 GB).

## Start and stop

`./start.sh` starts everything (and Docker if needed). `./stop.sh` shuts it down; your data is kept.
