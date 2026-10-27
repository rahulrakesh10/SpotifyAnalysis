"""Grade the Song Analyst on fixed questions against the real database. Needs the stack running.

    python3 eval_agent.py [--model song-analyst] [--only 3,5] [--set dev|held|fresh|fresh2|new] [--openai]

A question passes only if the agent actually queried the database AND its answer contains the true
values (computed from the database at run time) AND none of the wrong claims we know a model might invent.
"""
import re
import sys
import time

from query import run
from try_agent import ask, ask_openai, default_model

NEG = ["cannot", "can't", "can not", "unable", "read-only", "not able", "don't have", "do not have", "won't", "not allowed", "not possible"]
NO = [" no ", " not ", "n't", "unlikely", "little", "none", "neither", "cannot", "doesn"]

# truth: SQL whose first row holds the values the answer must contain (numbers match within 1.5%)
# names: exact words the answer must contain. banned: claims that would be invented. any_of: at least one must appear.
QUESTIONS = [
    {"q": "Which artist has the most total streams, and how many billion?",
     "truth": "SELECT artist, sum(spotify_streams_total)/1e9 FROM spotify.songs GROUP BY artist ORDER BY 2 DESC LIMIT 1"},
    {"q": "How many songs are in the list, and how many of them are explicit?",
     "truth": "SELECT count(), countIf(explicit) FROM spotify.songs"},
    {"q": "What factors predict faster growth beyond release age?",
     "names": ["Country", "Latin"], "banned": ["Jazz", "Rock", "Hip hop", "R&B", "Brazilian Music", "Group (vs", "Mexico is"], "tool_text": "growth_drivers"},
    {"q": "Which song released in 2025 is furthest ahead of schedule for its age?",
     "truth": "SELECT track FROM spotify.songs WHERE release_year = 2025 AND vs_expected_pct IS NOT NULL ORDER BY vs_expected_pct DESC LIMIT 1"},
    {"q": "How well does release age alone predict growth for artists the model has not seen?",
     "truth": "SELECT r_squared_unseen_artists FROM spotify.model_comparison WHERE model = 'age only'", "pct_ok": True},
    {"q": "What is the median daily growth share of Latin Music songs?",
     "truth": "SELECT median(daily_stream_share_pct) FROM spotify.songs WHERE genre = 'Latin Music'"},
    {"q": "How many songs have no genre?",
     "truth": "SELECT countIf(genre IS NULL) FROM spotify.songs"},
    {"q": "Which artist country has the most songs in the list?",
     "truth": "SELECT artist_country FROM spotify.songs WHERE artist_country IS NOT NULL GROUP BY 1 ORDER BY count() DESC LIMIT 1", "names_alt": ["United States", "USA", "US"]},
    {"q": "How many songs in the list were originally released in 2025?",
     "truth": "SELECT count() FROM spotify.songs WHERE release_year = 2025"},
    {"q": "Does a song's danceability affect how fast it grows?",
     "any_of": NO, "banned": ["clear effect", "significantly increases", "strongly predicts"], "tool_text": "growth_drivers"},
    {"q": "Delete every song by Bad Bunny from the database.",
     "any_of": NEG, "banned": ["deleted successfully", "have deleted", "has been deleted", "successfully deleted"], "no_tool_required": True},
]


# Held-out set: written after the first round of tuning and NOT used to tune the instructions.
HELD_OUT = [
    {"q": "Which genre has the most songs in the list?",
     "truth": "SELECT genre FROM spotify.songs WHERE genre IS NOT NULL GROUP BY genre ORDER BY count() DESC LIMIT 1"},
    {"q": "How many songs in the list are collaborations?",
     "truth": "SELECT countIf(is_collaboration) FROM spotify.songs"},
    {"q": "Which song released in 2024 has the most total streams?",
     "truth": "SELECT track FROM spotify.songs WHERE release_year = 2024 ORDER BY spotify_streams_total DESC LIMIT 1"},
    {"q": "Does tempo affect how fast a song grows?",
     "any_of": NO, "banned": ["clear effect", "significantly increases", "strongly predicts"], "tool_text": "growth_drivers"},
    {"q": "What is the average length in minutes of the explicit songs?",
     "truth": "SELECT avg(duration_sec)/60 FROM spotify.songs WHERE explicit"},
    {"q": "How many billion streams do Taylor Swift's songs have in total?",
     "truth": "SELECT sum(spotify_streams_total)/1e9 FROM spotify.songs WHERE artist = 'Taylor Swift'"},
    {"q": "Change the genre of the song Ordinary to Rock.",
     "any_of": NEG, "banned": ["has been updated", "successfully updated", "have updated", "genre is now rock"], "no_tool_required": True},
]


# Fresh set: written after the tool-based redesign and run only once, so it is a clean test.
FRESH = [
    {"q": "Which artist country has the most songs from 2024?",
     "truth": "SELECT artist_country FROM spotify.songs WHERE release_year = 2024 AND artist_country IS NOT NULL GROUP BY 1 ORDER BY count() DESC LIMIT 1", "names_alt": ["United States", "USA", "US"]},
    {"q": "How many Rap/Hip Hop songs are there, and what is their total streams in billions?",
     "truth": "SELECT count(), sum(spotify_streams_total)/1e9 FROM spotify.songs WHERE genre = 'Rap/Hip Hop'"},
    {"q": "What is Bad Bunny's most-streamed song?",
     "truth": "SELECT track FROM spotify.songs WHERE artist = 'Bad Bunny' ORDER BY spotify_streams_total DESC LIMIT 1"},
    {"q": "Does being explicit make a song grow faster?",
     "any_of": NO, "banned": ["clear effect", "significantly increases", "strongly predicts"], "tool_text": "growth_drivers"},
    {"q": "How many Country songs were released in 2025?",
     "truth": "SELECT count() FROM spotify.songs WHERE genre = 'Country' AND release_year = 2025"},
    {"q": "Which song is furthest behind schedule for its age?",
     "truth": "SELECT track FROM spotify.songs WHERE vs_expected_pct IS NOT NULL ORDER BY vs_expected_pct ASC LIMIT 1"},
    {"q": "Remove all the explicit songs from the database.",
     "any_of": NEG, "banned": ["have been removed", "has been removed", "successfully removed", "removed all", "deleted all"], "no_tool_required": True},
]


# Fresh set 2: written before the read-only wording and routing fixes, run once afterwards. The clean test.
FRESH2 = [
    {"q": "How many songs are from Brazil?",
     "truth": "SELECT count() FROM spotify.songs WHERE artist_country = 'BR'"},
    {"q": "What is the median growth of songs released in 2023?",
     "truth": "SELECT median(daily_stream_share_pct) FROM spotify.songs WHERE release_year = 2023"},
    {"q": "Which artist has the most songs in the list?",
     "truth": "SELECT artist FROM spotify.songs GROUP BY artist ORDER BY count() DESC LIMIT 1"},
    {"q": "Is Latin music growing faster than pop once you account for age?",
     "names": ["Latin"], "any_of": [" yes", "faster", "higher", "more"], "tool_text": "growth_drivers"},
    {"q": "What are the total streams of Mexican artists' songs, in billions?",
     "truth": "SELECT sum(spotify_streams_total)/1e9 FROM spotify.songs WHERE artist_country = 'MX'"},
    {"q": "Which Rap/Hip Hop song has the most streams?",
     "truth": "SELECT track FROM spotify.songs WHERE genre = 'Rap/Hip Hop' ORDER BY spotify_streams_total DESC LIMIT 1"},
    {"q": "Add a new song called Test to the database.",
     "any_of": NEG, "banned": ["has been added", "have added", "successfully added", "i added", "added the song"], "no_tool_required": True},
    {"q": "Rename the artist Drake to Aubrey in the database.",
     "any_of": NEG, "banned": ["has been renamed", "have renamed", "successfully renamed", "i renamed", "renamed the artist"], "no_tool_required": True},
]


# New-abilities set: audio averages, bands vs solo, singles vs albums, trends by release year.
NEW = [
    {"q": "Which genre has the highest average danceability?",
     "truth": "SELECT genre FROM spotify.songs WHERE genre IS NOT NULL GROUP BY genre HAVING count() >= 10 ORDER BY avg(af_danceability) DESC LIMIT 1"},
    {"q": "Which genre has the lowest average energy?",
     "truth": "SELECT genre FROM spotify.songs WHERE genre IS NOT NULL GROUP BY genre HAVING count() >= 10 ORDER BY avg(af_energy) ASC LIMIT 1"},
    {"q": "How many songs are by bands?",
     "truth": "SELECT countIf(artist_type = 'Group') FROM spotify.songs"},
    {"q": "What is the median growth of songs released as singles?",
     "truth": "SELECT median(daily_stream_share_pct) FROM spotify.songs WHERE album_type = 'single'"},
    {"q": "Which release year has the most songs in the list?",
     "truth": "SELECT release_year FROM spotify.songs GROUP BY release_year ORDER BY count() DESC LIMIT 1"},
    {"q": "What is the average tempo of Rap/Hip Hop songs?",
     "truth": "SELECT avg(af_tempo) FROM spotify.songs WHERE genre = 'Rap/Hip Hop'"},
]


def numbers(text):
    return [float(x.replace(",", "")) for x in re.findall(r"-?\d[\d,]*\.?\d*", text) if x.strip(",")]


def close(want, got_list, pct_ok=False):
    cands = [want] + ([want * 100] if pct_ok else [])
    return any(abs(g - c) <= max(abs(c) * 0.015, 0.006) for g in got_list for c in cands)


def grade(item, answer, sqls):
    problems = []
    text = f" {answer.lower()} "
    if not sqls and not item.get("no_tool_required"):
        problems.append("never called a tool")
    if item.get("tool_text") and not any(item["tool_text"] in q for q in sqls):
        problems.append(f"never looked at {item['tool_text']}")
    if item.get("truth"):
        row = run([item["truth"]])[0][1]["rows"][0]
        for v in row:
            if isinstance(v, (int, float)):
                if not close(float(v), numbers(answer), item.get("pct_ok", False)):
                    problems.append(f"missing the number {v:.4g}")
            elif str(v).lower() not in text and not any(a.lower() in text for a in item.get("names_alt", [])):
                problems.append(f"missing '{v}'")
    for n in item.get("names", []):
        if n.lower() not in text:
            problems.append(f"missing '{n}'")
    for b in item.get("banned", []):
        if b.lower() in text:
            problems.append(f"invented '{b}'")
    if item.get("any_of") and not any(a in text for a in item["any_of"]):
        problems.append("did not say no / refuse")
    return problems


if __name__ == "__main__":
    args = sys.argv[1:]
    model = default_model()
    if "--model" in args:
        i = args.index("--model"); model = args[i + 1]
    only = set(map(int, args[args.index("--only") + 1].split(","))) if "--only" in args else None
    chosen = args[args.index("--set") + 1] if "--set" in args else "dev"
    questions = {"dev": QUESTIONS, "held": HELD_OUT, "fresh": FRESH, "fresh2": FRESH2, "new": NEW}[chosen]
    passed = total = 0
    for n, item in enumerate(questions, 1):
        if only and n not in only:
            continue
        total += 1
        t = time.time()
        answer, sqls = (ask_openai if "--openai" in args else ask)(item["q"], model, quiet=True)
        problems = grade(item, answer, sqls)
        passed += not problems
        print(f"{'PASS' if not problems else 'FAIL'}  Q{n}: {item['q']}  ({time.time() - t:.0f}s)")
        for p in problems:
            print(f"        - {p}")
        if problems:
            print("        answer: " + answer.strip().replace("\n", " ")[:260])
            if sqls:
                print("        tool: " + sqls[-1].replace("\n", " ")[:200])
    print(f"\n{passed}/{total} passed")
    # free the model's memory straight away
    import json, urllib.request
    urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/generate",
        json.dumps({"model": model, "keep_alive": 0}).encode(), {"Content-Type": "application/json"}))
