# Example questions for the Song Analyst

Each was checked against the database with `python3 query.py "<sql>"`.

| Question | Where the answer comes from |
|---|---|
| Which artists have the most streams? | `songs`, group by artist (Bad Bunny first, 11.25B across 15 songs) |
| What drives growth beyond release age? | `model_effects` where `clear_after_adjustment = 1` (Country and Latin music, both about +52%) |
| How well does release age predict growth? | `model_comparison` (about 0.52 on artists the model had not seen) |
| Which 2025 songs are furthest ahead of schedule? | `songs.vs_expected_pct`, release_year = 2025 |
| Do collaborations grow faster than solo songs? | `songs`, group by `is_collaboration` (small group: 11 songs from 2025) |
| Which genres are the most danceable? | `songs`, `avg(af_danceability)`, only the songs that have audio features (623 of 730) |
| Does tempo matter? | `model_effects` where `factor ILIKE '%tempo%'` (no, not distinguishable from chance) |
| How many songs are explicit? | `avg(explicit)` (about 30%) |

Comparisons, rankings and trends should also come with a chart (rendered in the chat as an artifact).

Questions the data can't answer, and the agent should say so: why a song took off, anything about listeners, and anything about songs that never reached 100M streams.
