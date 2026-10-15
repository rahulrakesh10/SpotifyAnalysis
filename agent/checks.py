"""Smoke test for the agent's database. Needs the stack running (./start.sh), then:

    python3 checks.py

Checks the data against the CSVs it was loaded from, the model results against what we reported,
and that the agent's login really is read-only. Exits non-zero if anything fails.
"""
import csv
import sys
from pathlib import Path

from query import run

DATA = Path(__file__).resolve().parent.parent / "data"


def rows_in(name):
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# the genre list hard-coded in songs_mcp/server.py
import re
GENRES = re.findall(r'"([^"]+)"', re.search(r"Genre = Literal\[(.*?)\]", (Path(__file__).parent / "songs_mcp" / "server.py").read_text(), re.S).group(1))

songs_csv = rows_in("spotify_2025_enriched.csv")
growth_csv = rows_in("song_growth.csv")
effects_csv = rows_in("model_effects.csv")

SQL = {
    "songs": "SELECT count(), countIf(vs_expected_pct IS NULL), min(original_release_date), max(original_release_date) FROM spotify.songs",
    "types": "SELECT toTypeName(release_year), toTypeName(explicit), toTypeName(af_valence), toTypeName(original_release_date) FROM spotify.songs LIMIT 1",
    "clear": "SELECT factor FROM spotify.model_effects WHERE clear_after_adjustment = 1 ORDER BY factor",
    "effects": "SELECT count() FROM spotify.model_effects",
    "models": "SELECT r_squared_unseen_artists FROM spotify.model_comparison WHERE model = 'age only'",
    "top": "SELECT artist, count() AS n FROM spotify.songs GROUP BY artist ORDER BY sum(spotify_streams_total) DESC LIMIT 1",
    "hardy": "SELECT toYear(original_release_date) FROM spotify.songs WHERE track = 'Le temps de l\\'amour'",
    "genres": "SELECT groupArray(genre) FROM (SELECT DISTINCT genre FROM spotify.songs WHERE genre IS NOT NULL ORDER BY genre)",
    "drop": "DROP TABLE spotify.songs",
    "insert": "INSERT INTO spotify.songs (rank) VALUES (1)",
    "system": "SELECT count() FROM system.users",
}
out = dict(zip(SQL, run(list(SQL.values()))))
first = lambda key: out[key][1]["rows"][0] if out[key][0] else None

expected_growth_rows = len(growth_csv)
checks = [
    ("all songs loaded", first("songs") and first("songs")[0] == len(songs_csv), f"{first('songs')[0]} vs {len(songs_csv)} in CSV"),
    ("songs without growth match the model's coverage", first("songs") and first("songs")[1] == len(songs_csv) - expected_growth_rows,
     f"{first('songs')[1]} blank, expected {len(songs_csv) - expected_growth_rows}"),
    ("old release dates did not wrap around", first("songs") and first("songs")[2] < "1970-01-01" and first("songs")[3] < "2027-01-01",
     f"{first('songs')[2]} to {first('songs')[3]}"),
    ("column types are usable", first("types") and first("types")[0].startswith("Nullable(Int") and "UInt8" in first("types")[1]
     and "Float64" in first("types")[2] and "Date32" in first("types")[3], str(first("types"))),
    ("model_effects matches the CSV", first("effects") and first("effects")[0] == len(effects_csv), f"{first('effects')[0]} rows"),
    ("only Country and Latin Music hold up", out["clear"][0] and [r[0] for r in out["clear"][1]["rows"]] == ["Country", "Latin Music"],
     str(out["clear"][1]["rows"] if out["clear"][0] else out["clear"][1])),
    ("age explains about half on unseen artists", first("models") and 0.45 <= first("models")[0] <= 0.6, str(first("models"))),
    ("Bad Bunny leads with 15 songs", first("top") == ["Bad Bunny", 15], str(first("top"))),
    ("1962 song keeps its 1962 date", first("hardy") == [1962], str(first("hardy"))),
    ("song tools list every genre in the data", out["genres"][0] and sorted(first("genres")[0]) == sorted(GENRES), str(first("genres"))),
    ("agent cannot drop a table", not out["drop"][0] and "ACCESS_DENIED" in out["drop"][1], out["drop"][1][:60]),
    ("agent cannot insert rows", not out["insert"][0] and "ACCESS_DENIED" in out["insert"][1], out["insert"][1][:60]),
    ("agent cannot read system tables", not out["system"][0] and "ACCESS_DENIED" in out["system"][1], out["system"][1][:60]),
]

failed = 0
for name, ok, detail in checks:
    print(f"{'PASS' if ok else 'FAIL'}  {name}  ({detail})")
    failed += not ok
print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
sys.exit(1 if failed else 0)
