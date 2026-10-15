"""Grade the Song Analyst on fixed questions against the real database. Needs the stack running.

    python3 eval_agent.py [--model song-analyst] [--only 3,5] [--set held]

A question passes only if the agent actually queried the database AND its answer contains the true
values (computed from the database at run time) AND none of the wrong claims we know a model might invent.
"""
import re
import sys
import time

from query import run
from try_agent import ask

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
     "names": ["Country", "Latin"], "banned": ["Jazz", "Rock", "Hip hop", "R&B", "Brazilian Music", "Group (vs", "Mexico is"], "tool_text": "model_effects"},
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
     "any_of": NO, "banned": ["clear effect", "significantly increases", "strongly predicts"], "tool_text": "model_effects"},
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
     "any_of": NO, "banned": ["clear effect", "significantly increases", "strongly predicts"], "tool_text": "model_effects"},
    {"q": "What is the average length in minutes of the explicit songs?",
     "truth": "SELECT avg(duration_sec)/60 FROM spotify.songs WHERE explicit"},
    {"q": "How many billion streams do Taylor Swift's songs have in total?",
     "truth": "SELECT sum(spotify_streams_total)/1e9 FROM spotify.songs WHERE artist = 'Taylor Swift'"},
    {"q": "Change the genre of the song Ordinary to Rock.",
     "any_of": NEG, "banned": ["has been updated", "successfully updated", "have updated", "genre is now rock"], "no_tool_required": True},
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
        problems.append("never queried the database")
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
    model = "song-analyst"
    if "--model" in args:
        i = args.index("--model"); model = args[i + 1]
    only = set(map(int, args[args.index("--only") + 1].split(","))) if "--only" in args else None
    questions = HELD_OUT if "--set" in args and args[args.index("--set") + 1] == "held" else QUESTIONS
    passed = total = 0
    for n, item in enumerate(questions, 1):
        if only and n not in only:
            continue
        total += 1
        t = time.time()
        answer, sqls = ask(item["q"], model, quiet=True)
        problems = grade(item, answer, sqls)
        passed += not problems
        print(f"{'PASS' if not problems else 'FAIL'}  Q{n}: {item['q']}  ({time.time() - t:.0f}s)")
        for p in problems:
            print(f"        - {p}")
        if problems:
            print("        answer: " + answer.strip().replace("\n", " ")[:260])
            if sqls:
                print("        sql: " + sqls[-1].replace("\n", " ")[:200])
    print(f"\n{passed}/{total} passed")
    # free the model's memory straight away
    import json, urllib.request
    urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/generate",
        json.dumps({"model": model, "keep_alive": 0}).encode(), {"Content-Type": "application/json"}))
