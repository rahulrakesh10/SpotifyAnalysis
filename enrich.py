"""Enrich most_streamed_spotify_2025.csv with metadata from Deezer and MusicBrainz.

ReccoBeats (no key): Spotify-style audio features, looked up by ISRC.
Deezer (no key): release date, duration, explicit, loudness (gain), genre, label, record type, ISRC.
MusicBrainz (no key): earliest release date of the recording, artist country, artist type, career start year, genre tags.

API responses are cached in cache/ so reruns are fast and resumable.
"""
import json
import re
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).parent
SRC = ROOT / "data" / "most_streamed_spotify_2025.csv"
OUT = ROOT / "data" / "spotify_2025_enriched.csv"
CACHE = ROOT / "cache"
CACHE.mkdir(exist_ok=True)

session = requests.Session()
session.headers["User-Agent"] = "spotify-2025-enrichment/0.1 (personal research project)"
_last_call = {}


def get_json(url, params, host, min_interval):
    """GET with on-disk cache, per-host rate limiting and retries."""
    key = re.sub(r"[^A-Za-z0-9]+", "_", url + json.dumps(params, sort_keys=True))[:200]
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    for attempt in range(5):
        wait = min_interval - (time.time() - _last_call.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        _last_call[host] = time.time()
        try:
            r = session.get(url, params=params, timeout=20)
            if r.status_code in (429, 503):
                time.sleep(2 ** attempt)
                continue
            data = r.json()
            # Deezer signals quota errors in the body
            if isinstance(data, dict) and data.get("error", {}).get("code") == 4:
                time.sleep(2 ** attempt)
                continue
            path.write_text(json.dumps(data))
            return data
        except (requests.RequestException, ValueError):
            time.sleep(2 ** attempt)
    return None


def norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r"\s*[\(\[][^\)\]]*(feat|with|ft\.)[^\)\]]*[\)\]]", "", s)
    s = re.sub(r"\s+-\s+.*(remaster|version|edit).*$", "", s)
    return re.sub(r"[\W_]+", " ", s).strip()


def sim(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


def deezer(path, params=None):
    return get_json(f"https://api.deezer.com/{path}", params or {}, "deezer", 0.12)


ARTIST_ALIASES = {"mgk": "Machine Gun Kelly"}


def match_deezer(track, artist):
    best, best_score = None, 0.0
    queries = (f"{track} {artist}", f'track:"{track}" artist:"{artist}"', f'artist:"{artist}"', track)
    for q in queries:
        res = deezer("search", {"q": q, "limit": 15}) or {}
        for cand in res.get("data", []):
            score = 0.6 * sim(track, cand["title"]) + 0.4 * sim(artist, cand["artist"]["name"])
            if sim(track, cand["title"]) < 0.6:
                continue
            if score > best_score:
                best, best_score = cand, score
        if best_score >= 0.95:
            break
    return best, round(best_score, 3)


def enrich_track(track, artist):
    artist = ARTIST_ALIASES.get(artist, artist)
    cand, score = match_deezer(track, artist)
    row = {"dz_match_score": score, "dz_artist_match": bool(cand) and sim(artist, cand["artist"]["name"]) >= 0.85}
    # Title-only matches are usually covers with the wrong release date; skip them
    if not cand or score < 0.6 or not row["dz_artist_match"]:
        return row
    t = deezer(f"track/{cand['id']}") or {}
    album = deezer(f"album/{cand['album']['id']}") or {}
    genres = [g["name"] for g in album.get("genres", {}).get("data", [])]
    row.update(
        dz_track_id=cand["id"],
        dz_title=cand["title"],
        dz_artist=cand["artist"]["name"],
        isrc=t.get("isrc"),
        release_date=t.get("release_date") or album.get("release_date"),
        duration_sec=t.get("duration"),
        explicit=t.get("explicit_lyrics"),
        loudness_gain_db=t.get("gain"),
        bpm=t.get("bpm") or None,  # Deezer uses 0 for unknown
        dz_popularity_rank=t.get("rank"),
        album_type=album.get("record_type"),
        album_tracks=album.get("nb_tracks"),
        label=album.get("label"),
        genre=genres[0] if genres else None,
        genres_all="|".join(genres) or None,
    )
    return row


# MusicBrainz sometimes gives a city/region area instead of a country code
AREA_TO_COUNTRY = {
    "Culiacán": "MX", "Guadalajara": "MX", "Mazatlan": "MX", "Hermosillo": "MX", "Tamaulipas": "MX", "Guadalupe": "MX",
    "England": "GB", "Liverpool": "GB", "Scotland": "GB", "Belfast": "GB",
    "Punjab": "IN", "Chennai": "IN", "Mumbai": "IN", "Tamil Nadu": "IN", "Uttarakhand": "IN", "Hyderabad": "IN",
    "Houston": "US", "Salinas": "US", "New York": "US", "Philadelphia": "US", "Dallas": "US", "Florida": "US",
    "Los Angeles": "US", "St. Louis": "US", "Miami": "US", "Nashville": "US", "Pittsburg": "US", "Orange County": "US",
    "Pennsylvania": "US", "Brooklyn": "US", "Montgomery": "US",
    "Rio de Janeiro": "BR", "Ceará": "BR", "Goiás": "BR", "Medellín": "CO", "Esmeraldas": "EC", "Santo Domingo": "DO",
    "Santiago": "CL", "Bayamón": "PR", "Lüneburg": "DE", "Savona": "IT", "Melbourne": "AU", "Nanaimo": "CA",
    "Davao City": "PH", "Tacloban": "PH", "Sukth": "AL",
}


def mb_artist(name):
    name = ARTIST_ALIASES.get(name, name)
    res = get_json(
        "https://musicbrainz.org/ws/2/artist",
        {"query": f'artist:"{name}"', "fmt": "json", "limit": 5},
        "musicbrainz",
        1.1,
    ) or {}
    best = None
    for a in res.get("artists", []):
        if a.get("score", 0) >= 85 and sim(name, a["name"]) >= 0.85:
            best = a
            break
    if not best:
        return {}
    tags = sorted(best.get("tags", []), key=lambda t: -t.get("count", 0))
    return {
        "artist_country": best.get("country")
        or AREA_TO_COUNTRY.get((best.get("area") or {}).get("name"), (best.get("area") or {}).get("name")),
        "artist_type": best.get("type"),
        "artist_begin_year": (best.get("life-span", {}).get("begin") or "")[:4] or None,
        "artist_tags": "|".join(t["name"] for t in tags[:5]) or None,
    }


AUDIO_FEATURES = ["danceability", "energy", "valence", "acousticness", "instrumentalness",
                  "liveness", "speechiness", "tempo", "loudness", "key", "mode"]


def reccobeats(path, params=None):
    return get_json(f"https://api.reccobeats.com/v1/{path}", params or {}, "reccobeats", 0.25)


def audio_features(isrc):
    if not isinstance(isrc, str):
        return {}
    res = reccobeats("track", {"ids": isrc}) or {}
    tracks = [t for t in res.get("content", []) if t.get("isrc") == isrc]
    if not tracks:
        return {}
    feats = reccobeats(f"track/{tracks[0]['id']}/audio-features") or {}
    if "danceability" not in feats:
        return {}
    row = {f"af_{k}": feats.get(k) for k in AUDIO_FEATURES}
    row["spotify_track_id"] = tracks[0].get("href", "").rsplit("/", 1)[-1] or None
    return row


def mb_first_release(track, artist):
    """Earliest first-release-date across MusicBrainz recordings of this title by this artist.

    Deezer often returns a remaster/compilation date for older songs; MusicBrainz tracks the original.
    """
    artist = ARTIST_ALIASES.get(artist, artist)
    clean = lambda x: re.sub(r'["\\]', " ", x)
    title = re.sub(r"\s*[\(\[].*?[\)\]]", "", track).strip() or track  # drop "(feat. ...)", "(From ...)"
    res = get_json(
        "https://musicbrainz.org/ws/2/recording",
        {"query": f'recording:"{clean(title)}" AND artist:"{clean(artist)}"', "fmt": "json", "limit": 25},
        "musicbrainz",
        1.1,
    ) or {}
    dates = []
    for rec in res.get("recordings", []):
        credit = " ".join(c.get("name", "") for c in rec.get("artist-credit", []))
        if (rec.get("score", 0) >= 80 and sim(title, rec["title"]) >= 0.9
                and (sim(artist, credit) >= 0.85 or norm(artist) in norm(credit))
                and len(rec.get("first-release-date") or "") >= 4):
            dates.append(rec["first-release-date"])
    # Year-only dates ("1975") sort before full dates in the same year, which is what we want
    return min(dates) if dates else None


# Reissues of old songs that carry a new (2024+) ISRC, checked by hand. For other new ISRCs, a much
# older MusicBrainz date is a different song with the same title (e.g. LISA "Born Again" -> 2007).
VERIFIED_REISSUES = {
    ("Silly Love Songs", "Wings"), ("Always Somewhere", "Scorpions"),
    ("La Guitarra (Remasterizado 2025)", "Los Auténticos Decadentes"), ("Shatter Me", "Lindsey Stirling"),
}


def isrc_year(isrc):
    """ISRCs are CC-XXX-YY-NNNNN; YY is the year the code was assigned."""
    if not isinstance(isrc, str) or not isrc[5:7].isdigit():
        return None
    yy = int(isrc[5:7])
    return 1900 + yy if yy >= 40 else 2000 + yy


def main():
    df = pd.read_csv(SRC)

    track_rows = []
    for i, r in df.iterrows():
        track_rows.append(enrich_track(r["track"], r["artist"]))
        if (i + 1) % 50 == 0:
            print(f"deezer {i + 1}/{len(df)}", flush=True)
    df = pd.concat([df, pd.DataFrame(track_rows)], axis=1)

    feats = []
    for i, isrc in enumerate(df["isrc"]):
        feats.append(audio_features(isrc))
        if (i + 1) % 100 == 0:
            print(f"reccobeats {i + 1}/{len(df)}", flush=True)
    df = pd.concat([df, pd.DataFrame(feats, index=df.index)], axis=1)

    artists = df["artist"].unique()
    artist_info = {}
    for i, name in enumerate(artists):
        artist_info[name] = mb_artist(name)
        if (i + 1) % 50 == 0:
            print(f"musicbrainz {i + 1}/{len(artists)}", flush=True)
    df = df.join(pd.DataFrame.from_dict(artist_info, orient="index"), on="artist")

    mb_dates = []
    for i, r in df.iterrows():
        mb_dates.append(mb_first_release(r["track"], r["artist"]))
        if (i + 1) % 100 == 0:
            print(f"musicbrainz dates {i + 1}/{len(df)}", flush=True)
    df["mb_first_release"] = mb_dates

    # Derived features
    snapshot = pd.Timestamp("2026-07-15")  # date the source file was produced
    dz = pd.to_datetime(df["release_date"], errors="coerce")
    # MusicBrainz dates can be partial ("1975", "2025-02"); pad to the first of the year/month
    pad = lambda d: d + "-01-01"[len(d) - 4:] if isinstance(d, str) else None
    mb = pd.to_datetime(df["mb_first_release"].map(pad), errors="coerce")
    iy = df["isrc"].map(isrc_year)
    reissue = pd.Series([(t, a) in VERIFIED_REISSUES for t, a in zip(df["track"], df["artist"])], index=df.index)
    # Trust an earlier MusicBrainz date when it fits the ISRC, the ISRC is old catalog, or it's a verified reissue
    mb_ok = mb.notna() & ((mb.dt.year >= iy - 1) | (iy <= 2023) | iy.isna() | reissue)
    mb = mb.where(mb_ok)
    rd = pd.concat([dz, mb], axis=1).min(axis=1)
    rd = rd.where(rd <= snapshot)  # a date after the snapshot is a later reissue we couldn't resolve
    df["original_release_date"] = rd.dt.date
    df["date_source"] = np.select([rd.isna(), mb.notna() & ((mb < dz) | dz.isna())], [None, "musicbrainz"], "deezer")
    df["release_year"] = rd.dt.year
    df["days_since_release"] = (snapshot - rd).dt.days
    df["momentum"] = df["rank"] - df["daily_streams_rank"]  # >0 = rising, <0 = fading

    df.to_csv(OUT, index=False)
    print(f"\nwrote {OUT}")
    print(f"deezer matched: {df['dz_track_id'].notna().sum()}/{len(df)}")
    print(f"audio features found: {df['af_energy'].notna().sum()}/{len(df)}")
    print(f"artist country found: {df['artist_country'].notna().sum()}/{len(df)} rows")


if __name__ == "__main__":
    main()
