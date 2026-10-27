"""Song tools for the agent: ready-made, parameterized queries.

A small model is unreliable at writing SQL (stray quotes, wrong columns, half-answered questions).
These tools take simple parameters instead, bind them safely, and return plain numbers plus a note on
how to read them. Read-only: the database login can only SELECT.
"""
import functools
import inspect
import os
from typing import Literal, Optional, Union, get_args

import clickhouse_connect
from fastmcp import FastMCP
from fastmcp.server.auth import StaticTokenVerifier
from fastmcp.server.middleware import Middleware

COUNTRY_NAMES = {
    "united states": "US", "usa": "US", "america": "US", "mexico": "MX", "brazil": "BR", "united kingdom": "GB",
    "uk": "GB", "england": "GB", "canada": "CA", "south korea": "KR", "korea": "KR", "india": "IN",
    "puerto rico": "PR", "colombia": "CO", "france": "FR", "indonesia": "ID", "sweden": "SE", "germany": "DE",
    "argentina": "AR", "spain": "ES", "japan": "JP", "australia": "AU", "philippines": "PH", "italy": "IT",
}

# The genres in the data. Listing them lets the tool reject a wrong one (like "Brazil", which is a country)
# and show the valid choices, instead of silently matching the wrong thing. checks.py verifies this list.
Genre = Literal["Pop", "Rap/Hip Hop", "Latin Music", "Asian Music", "Alternative", "Brazilian Music", "Country",
                "Electro", "Dance", "R&B", "Rock", "Indian Music", "African Music", "Bolero", "Classical",
                "Films/Games", "French Chanson", "Reggae", "Singer & Songwriter", "Soul & Funk"]

GENRES = list(get_args(Genre))

_client = None


def db():
    global _client
    if _client is None:
        _client = clickhouse_connect.get_client(
            host=os.environ["CLICKHOUSE_HOST"], port=int(os.environ.get("CLICKHOUSE_PORT", "8123")),
            username=os.environ["CLICKHOUSE_USER"], password=os.environ["CLICKHOUSE_PASSWORD"], database="spotify")
    return _client


def rows(sql, params=None):
    result = db().query(sql, parameters=params or {})
    return [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in result.named_results()]


def song_filter(genre=None, artist=None, artist_country=None, release_year=None, explicit=None, collaboration=None,
                album_type=None, artist_type=None):
    """Optional filters -> (WHERE clause, bound parameters, readable description)."""
    conds, params, used = [], {}, {}
    if genre:
        conds.append("lower(genre) = lower({genre:String})"); params["genre"] = genre; used["genre"] = genre
    if artist:
        conds.append("lower(artist) = lower({artist:String})"); params["artist"] = artist; used["artist"] = artist
    if artist_country:
        code = COUNTRY_NAMES.get(artist_country.strip().lower(), artist_country.strip().upper())
        conds.append("artist_country = {country:String}"); params["country"] = code; used["artist_country"] = code
    if release_year is not None:
        conds.append("release_year = {year:Int32}"); params["year"] = int(release_year); used["release_year"] = int(release_year)
    if explicit is not None:
        conds.append("explicit = {explicit:UInt8}"); params["explicit"] = int(bool(explicit)); used["explicit"] = bool(explicit)
    if collaboration is not None:
        conds.append("is_collaboration = {collab:UInt8}"); params["collab"] = int(bool(collaboration)); used["collaboration"] = bool(collaboration)
    if album_type:
        conds.append("album_type = {album:String}"); params["album"] = album_type; used["album_type"] = album_type
    if artist_type:
        conds.append("artist_type = {atype:String}"); params["atype"] = artist_type; used["artist_type"] = artist_type
    return (" WHERE " + " AND ".join(conds)) if conds else "", params, used


def describe(used):
    """'artist=Taylor Swift, release_year=2025' for the summary sentences."""
    return ", ".join(f"{k}={v}" for k, v in used.items()) if isinstance(used, dict) else "all songs"


def billions(n):
    return f"{n:.2f} billion" if n is not None else "n/a"


class BadInput(Exception):
    """A value the tool cannot use. Returned to the model as a normal answer so it can retry."""


VALID = {"group_by": ["artist", "genre", "artist_country", "release_year", "album_type", "artist_type"],
         "measure": ["total_streams", "song_count", "median_growth", "avg_danceability", "avg_energy", "avg_valence",
                     "avg_tempo", "avg_length_minutes"],
         "order": ["highest", "lowest"], "direction": ["ahead", "behind"], "sort_by": ["total_streams", "growth"],
         "column": ["genre", "artist_country"]}
ALBUM_TYPES = {"single": "single", "singles": "single", "album": "album", "albums": "album", "ep": "ep", "eps": "ep",
               "compile": "compile", "compilation": "compile", "compilations": "compile"}
ARTIST_TYPES = {"solo": "Person", "solo artist": "Person", "person": "Person", "individual": "Person", "soloist": "Person",
                "group": "Group", "band": "Group", "bands": "Group", "groups": "Group", "duo": "Group"}
MEASURE_ALIASES = {"danceability": "avg_danceability", "energy": "avg_energy", "valence": "avg_valence", "mood": "avg_valence",
                   "tempo": "avg_tempo", "length": "avg_length_minutes", "growth": "median_growth", "streams": "total_streams",
                   "songs": "song_count", "count": "song_count"}


def as_int(name, v):
    try:
        return int(float(str(v).strip()))
    except ValueError:
        raise BadInput(f"{name} must be a whole number, but got '{v}'.")


def as_bool(name, v):
    if isinstance(v, bool):
        return v
    text = str(v).strip().lower()
    if text in ("true", "yes", "y", "1"):
        return True
    if text in ("false", "no", "n", "0"):
        return False
    raise BadInput(f"{name} must be true or false, but got '{v}'.")


def coerce(kwargs):
    """Models send numbers and booleans as text and get option names slightly wrong. Fix what is fixable and
    explain the rest. LibreChat checks the input type before the call, so the tool schemas accept text too."""
    out = {}
    for k, v in kwargs.items():
        if v is None:            # an option the model did not use
            out[k] = None
        elif k == "limit":
            out[k] = max(1, min(as_int(k, v), 25))
        elif k == "release_year":
            out[k] = as_int(k, v)
        elif k in ("explicit", "collaboration"):
            out[k] = as_bool(k, v)
        elif k == "album_type":
            out[k] = ALBUM_TYPES.get(str(v).strip().lower()) or (_ for _ in ()).throw(
                BadInput(f"album_type must be one of: single, album, ep, compile. Got '{v}'."))
        elif k == "artist_type":
            out[k] = ARTIST_TYPES.get(str(v).strip().lower()) or (_ for _ in ()).throw(
                BadInput(f"artist_type must be solo or group. Got '{v}'."))
        elif k == "genre":
            match = next((g for g in GENRES if g.lower() == str(v).strip().lower()), None)
            if match is None:
                hint = " That is a country: use artist_country." if str(v).strip().lower() in COUNTRY_NAMES else ""
                raise BadInput(f"'{v}' is not a genre.{hint} Genres: {', '.join(GENRES)}.")
            out[k] = match
        elif k in VALID:
            text = str(v).strip().lower().replace(" ", "_")
            if k == "measure":
                text = MEASURE_ALIASES.get(text, text)
            match = next((o for o in VALID[k] if o == text), None)
            if match is None:
                raise BadInput(f"{k} must be one of: {', '.join(VALID[k])}. Got '{v}'.")
            out[k] = match
        else:
            out[k] = v
    return out


NULLISH = {"", "null", "none", "nil", "n/a", "na", "any", "all", "undefined", "unspecified"}
TOOL_PARAMS = {}   # tool name -> the parameters it really has


class CleanArguments(Middleware):
    """Small models send the text "null" for options they are not using and add parameters the tool does not
    have. Both would be errors, so drop them before the tool runs."""

    async def on_call_tool(self, context, call_next):
        args = context.message.arguments or {}
        allowed = TOOL_PARAMS.get(context.message.name)
        context.message.arguments = {
            k: v for k, v in args.items()
            if (allowed is None or k in allowed) and not (v is None or (isinstance(v, str) and v.strip().lower() in NULLISH))}
        return await call_next(context)

    async def on_list_tools(self, context, call_next):
        """Publish schemas that allow extra options. LibreChat rejects an unexpected option before the call
        ever reaches this server, so a small model that adds one would get an error; the call above drops them."""
        tools = await call_next(context)
        for t in tools:
            t.parameters["additionalProperties"] = True
        return tools


def tool(fn):
    TOOL_PARAMS[fn.__name__] = set(inspect.signature(fn).parameters)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **coerce(kwargs))
        except BadInput as e:
            return {"summary": str(e)}
    return mcp.tool(wrapper)


tokens = {os.environ["MCP_AUTH_TOKEN"]: {"client_id": "agent", "scopes": []}}
mcp = FastMCP("song-tools", auth=StaticTokenVerifier(tokens=tokens))
mcp.add_middleware(CleanArguments())


@tool
def song_stats(genre: Optional[str] = None, artist: Optional[str] = None, artist_country: Optional[str] = None,
               release_year: Optional[Union[int, str]] = None, explicit: Optional[Union[bool, str]] = None,
               collaboration: Optional[Union[bool, str]] = None, album_type: Optional[str] = None,
               artist_type: Optional[str] = None) -> dict:
    """Genres: Pop, Rap/Hip Hop, Latin Music, Asian Music, Alternative, Brazilian Music, Country, Electro, Dance, R&B, Rock, Indian Music, African Music, Bolero, Classical, Films/Games, French Chanson, Reggae, Singer & Songwriter, Soul & Funk. release_year is a number like 2025; explicit and collaboration are true or false; album_type is single, album, ep or compile (singles are songs released as a single); artist_type is solo or group (a group is a band). Statistics for a group of songs, with every filter optional. With no filters it covers all 730 songs.
    Returns: number of songs, total streams in billions, median growth (today's streams as a percent of all-time streams),
    average length in minutes, average audio features (danceability, energy, mood, tempo), explicit songs, collaboration songs, and how many songs lack a genre, country or audio features.
    Use for: how many songs, total streams of an artist or genre, median growth of a group, average length, average danceability, energy or tempo of a group, counts of explicit songs, bands versus solo artists, singles versus albums."""
    where, params, used = song_filter(genre, artist, artist_country, release_year, explicit, collaboration, album_type, artist_type)
    out = rows(f"""SELECT count() AS songs, round(sum(spotify_streams_total)/1e9, 3) AS total_streams_billions,
        median(daily_stream_share_pct) AS median_growth_pct, round(avg(duration_sec)/60, 2) AS avg_length_minutes,
        round(avg(af_danceability), 3) AS avg_danceability, round(avg(af_energy), 3) AS avg_energy,
        round(avg(af_valence), 3) AS avg_valence, round(avg(af_tempo), 1) AS avg_tempo_bpm,
        countIf(explicit) AS explicit_songs, countIf(is_collaboration) AS collaboration_songs,
        countIf(genre IS NULL) AS songs_missing_genre, countIf(artist_country IS NULL) AS songs_missing_country,
        countIf(af_energy IS NULL) AS songs_missing_audio_features FROM songs{where}""", params)[0]
    gaps = {k: out.pop(k) for k in ("songs_missing_genre", "songs_missing_country", "songs_missing_audio_features")}
    where_text = describe(used) if used else "all songs"
    audio = ("" if out["avg_danceability"] is None else
             f" Average audio: danceability {out['avg_danceability']}, energy {out['avg_energy']}, "
             f"mood (valence) {out['avg_valence']}, tempo {out['avg_tempo_bpm']} BPM.")
    summary = (f"{out['songs']} songs match ({where_text}). Total streams {billions(out['total_streams_billions'])}; "
               f"median growth {out['median_growth_pct']}% of all-time streams per day; average length {out['avg_length_minutes']} minutes; "
               f"{out['explicit_songs']} explicit; {out['collaboration_songs']} collaborations; "
               f"{gaps['songs_missing_genre']} have no genre.{audio}") if out["songs"] else "No songs match."
    if used and out["songs"]:
        # A small model often adds a filter it should not (for example explicit=true when asked "how many songs, and
        # how many are explicit?"). Always state the whole-list totals so the right numbers are in the answer anyway.
        whole = rows("SELECT count() AS songs, countIf(explicit) AS explicit_songs, countIf(is_collaboration) AS collaboration_songs FROM songs")[0]
        summary += (f" For reference, the whole list (no filters) has {whole['songs']} songs, "
                    f"{whole['explicit_songs']} explicit and {whole['collaboration_songs']} collaborations.")
    result = {"summary": summary, "filters_used": used or "none (all songs)", **out, "data_gaps": gaps}
    if out["songs"] == 0:
        result["note"] = "No songs match these filters. Check the spelling with find_songs or list_values."
    return result


@tool
def top_groups(group_by: str = "artist", measure: str = "total_streams", limit: Union[int, str] = 5,
               release_year: Optional[Union[int, str]] = None, order: str = "highest") -> dict:
    """group_by is artist, genre, artist_country, release_year, album_type or artist_type. measure is total_streams, song_count, median_growth, avg_danceability, avg_energy, avg_valence, avg_tempo or avg_length_minutes. order is highest (default) or lowest. release_year is a number like 2025.
    Rank groups of songs. group_by picks what to compare (for example genre, or solo versus group, or singles versus albums, or release year); measure picks how: total_streams (sum of all-time streams), song_count, median_growth, or the average danceability, energy, mood (valence), tempo or length. Groups with fewer than 10 songs are skipped for growth and audio measures. Optionally limit to one release_year.
    Use for: which artist, genre, country or year has the most streams or songs, the fastest-growing genre, which genre is most danceable or energetic, the lowest or least of something, songs per release year, singles versus albums, bands versus solo artists."""
    columns = {"total_streams": "total_streams_billions", "song_count": "songs", "median_growth": "median_growth_pct",
               "avg_danceability": "avg_danceability", "avg_energy": "avg_energy", "avg_valence": "avg_valence",
               "avg_tempo": "avg_tempo_bpm", "avg_length_minutes": "avg_length_minutes"}
    column = columns[measure]
    cond = f"WHERE {group_by} IS NOT NULL" + (" AND release_year = {year:Int32}" if release_year is not None else "")
    having = "HAVING songs >= 10" if measure not in ("total_streams", "song_count") else ""
    direction = "ASC" if order == "lowest" else "DESC"
    params = {"year": int(release_year)} if release_year is not None else {}
    data = rows(f"""SELECT {group_by} AS name, count() AS songs, round(sum(spotify_streams_total)/1e9, 3) AS total_streams_billions,
        median(daily_stream_share_pct) AS median_growth_pct, round(avg(af_danceability), 3) AS avg_danceability,
        round(avg(af_energy), 3) AS avg_energy, round(avg(af_valence), 3) AS avg_valence, round(avg(af_tempo), 1) AS avg_tempo_bpm,
        round(avg(duration_sec)/60, 2) AS avg_length_minutes FROM songs {cond} GROUP BY {group_by} {having}
        ORDER BY {column} {direction} LIMIT {max(1, min(int(limit), 25))}""", params)
    label = {"total_streams": "{} total streams", "song_count": "{} songs", "median_growth": "median growth {}%",
             "avg_danceability": "average danceability {}", "avg_energy": "average energy {}", "avg_valence": "average mood (valence) {}",
             "avg_tempo": "average tempo {} BPM", "avg_length_minutes": "average length {} minutes"}[measure]
    parts = [f"{i}) {r['name']}: " + label.format(billions(r[column]) if measure == "total_streams" else r[column]) + ("" if measure == "song_count" else f" ({r['songs']} songs)")
             for i, r in enumerate(data, 1)]
    summary = (f"{order.capitalize()} {group_by} by {measure.replace('_', ' ')}" + (f" (released {release_year})" if release_year else "")
               + ": " + "; ".join(parts))
    return {"summary": summary, "ranked_by": measure, "group_by": group_by, "release_year": release_year, "rows": data}


@tool
def top_songs(sort_by: str = "total_streams", limit: Union[int, str] = 5, release_year: Optional[Union[int, str]] = None,
              genre: Optional[str] = None, artist: Optional[str] = None, artist_country: Optional[str] = None) -> dict:
    """sort_by is total_streams or growth. Genres: Pop, Rap/Hip Hop, Latin Music, Asian Music, Alternative, Brazilian Music, Country, Electro, Dance, R&B, Rock, Indian Music, African Music, Bolero, Classical, Films/Games, French Chanson, Reggae, Singer & Songwriter, Soul & Funk. The biggest individual songs, by all-time total_streams or by current growth (today's streams as a percent of all-time streams).
    Optionally limit to a release_year, genre, artist or artist_country.
    Use for: which song has the most streams, the most-streamed song of a year, the fastest-growing songs."""
    where, params, used = song_filter(genre=genre, artist=artist, artist_country=artist_country, release_year=release_year)
    order = "spotify_streams_total" if sort_by == "total_streams" else "daily_stream_share_pct"
    data = rows(f"""SELECT track, artist, genre, original_release_date AS released, spotify_streams_total AS total_streams,
        daily_stream_share_pct AS growth_pct FROM songs{where} ORDER BY {order} DESC LIMIT {max(1, min(int(limit), 25))}""", params)
    parts = [f"{i}) {r['track']} by {r['artist']} ({r['released']}): {r['total_streams']:,} total streams, growth {r['growth_pct']}%"
             for i, r in enumerate(data, 1)]
    summary = f"Top songs by {sort_by.replace('_', ' ')} ({describe(used) if used else 'all songs'}): " + "; ".join(parts)
    return {"summary": summary, "sorted_by": sort_by, "filters_used": used or "none", "rows": data}


@tool
def ahead_or_behind(direction: str = "ahead", limit: Union[int, str] = 5, release_year: Optional[Union[int, str]] = None,
                          genre: Optional[str] = None) -> dict:
    """direction is ahead or behind. Genres: Pop, Rap/Hip Hop, Latin Music, Asian Music, Alternative, Brazilian Music, Country, Electro, Dance, R&B, Rock, Indian Music, African Music, Bolero, Classical, Films/Games, French Chanson, Reggae, Singer & Songwriter, Soul & Funk. Songs growing fastest (ahead) or slowest (behind) compared with what is typical for songs of their age.
    vs_expected_pct of +100 means growing twice as fast as expected for its age. Optionally filter by release_year or genre.
    Use for: which songs are ahead of or behind schedule, biggest risers or fallers for their age."""
    where, params, used = song_filter(genre=genre, release_year=release_year)
    where = (where + " AND" if where else " WHERE") + " vs_expected_pct IS NOT NULL"
    order = "DESC" if direction == "ahead" else "ASC"
    data = rows(f"""SELECT track, artist, genre, original_release_date AS released, round(vs_expected_pct) AS vs_expected_pct,
        daily_stream_share_pct AS growth_pct FROM songs{where} ORDER BY vs_expected_pct {order} LIMIT {max(1, min(int(limit), 25))}""", params)
    parts = [f"{i}) {r['track']} by {r['artist']}: {r['vs_expected_pct']:+.0f}% versus expected for its age" for i, r in enumerate(data, 1)]
    summary = f"Songs {direction} of schedule ({describe(used) if used else 'all songs'}): " + "; ".join(parts)
    return {"summary": summary, "direction": direction, "filters_used": used or "none", "rows": data}


@tool
def find_songs(text: str, limit: Union[int, str] = 10) -> dict:
    """Look up songs whose title or artist contains the text (not case sensitive). Returns track, artist, genre, release date,
    total streams, growth and vs_expected_pct. Use for: questions about one named song or artist's songs."""
    data = rows(f"""SELECT track, artist, genre, original_release_date AS released, spotify_streams_total AS total_streams,
        daily_stream_share_pct AS growth_pct, round(vs_expected_pct) AS vs_expected_pct FROM songs
        WHERE positionCaseInsensitive(track, {{t:String}}) > 0 OR positionCaseInsensitive(artist, {{t:String}}) > 0
        ORDER BY spotify_streams_total DESC LIMIT {max(1, min(int(limit), 25))}""", {"t": text})
    parts = [f"{r['track']} by {r['artist']} ({r['released']}): {r['total_streams']:,} streams, {r['vs_expected_pct']:+.0f}% vs expected for its age"
             if r['vs_expected_pct'] is not None else f"{r['track']} by {r['artist']} ({r['released']}): {r['total_streams']:,} streams"
             for r in data]
    return {"summary": f"{len(data)} songs match '{text}': " + "; ".join(parts) if data else f"No songs match '{text}'.", "search": text, "rows": data}


@tool
def growth_drivers(factor: Optional[str] = None) -> dict:
    """What predicts faster growth once release age is accounted for. With no factor, returns only the factors that clearly hold up.
    With a factor name (for example tempo, danceability, energy, Pop, Country, Brazil, explicit, collaboration), returns that factor's result.
    effect_pct is the percent difference in growth versus a baseline, holding age and everything else fixed. A factor with
    holds_up = false could be chance, so do not call it a real effect.
    Use for: what drives growth, does X matter, does X affect growth."""
    if factor:
        data = rows("""SELECT factor_group, factor, round(effect_pct, 1) AS effect_pct, round(ci_low_pct, 1) AS range_low_pct,
            round(ci_high_pct, 1) AS range_high_pct, toBool(clear_after_adjustment = 1) AS holds_up
            FROM model_effects WHERE positionCaseInsensitive(factor, {f:String}) > 0 ORDER BY effect_pct DESC""", {"f": factor})
        if not data:
            return {"summary": f"No factor named '{factor}'. Call growth_drivers with no factor to see the ones that hold up.", "factor": factor, "rows": []}
        parts = [f"{r['factor']}: {r['effect_pct']:+.1f}% (range {r['range_low_pct']:+.1f}% to {r['range_high_pct']:+.1f}%), "
                 + ("holds up after adjusting for chance" if r["holds_up"] else "NOT a proven effect, could be chance") for r in data]
        summary = "Effect on growth, holding release age and other factors fixed: " + "; ".join(parts)
    else:
        data = rows("""SELECT factor_group, factor, round(effect_pct, 1) AS effect_pct, round(ci_low_pct, 1) AS range_low_pct,
            round(ci_high_pct, 1) AS range_high_pct, true AS holds_up FROM model_effects
            WHERE clear_after_adjustment = 1 ORDER BY effect_pct DESC""")
        summary = ("Only these factors clearly predict faster growth after accounting for release age: "
                   + "; ".join(f"{r['factor']} ({r['effect_pct']:+.1f}%)" for r in data) + ". No other factor holds up; they could be chance.")
    return {"summary": summary, "factor": factor or "all factors that hold up", "rows": data, "note":
            "Baselines: genre vs Pop, country vs US, release format vs album track; audio features per 1 standard deviation."}


@tool
def model_fit() -> dict:
    """How well the growth model predicts. r_squared_unseen_artists is the honest number: 0.5 means release age explains
    about half the variation in growth, tested on artists the model had not seen. Use for: how well does age/the model predict."""
    data = rows("SELECT model, songs, round(r_squared, 3) AS r_squared, round(r_squared_unseen_artists, 3) AS r_squared_unseen_artists FROM model_comparison")
    age = next(r for r in data if r["model"] == "age only")
    summary = (f"Release age alone explains about {age['r_squared_unseen_artists'] * 100:.0f}% of the variation in growth for artists the model had "
               f"not seen (R-squared {age['r_squared_unseen_artists']}). Adding genre, country and audio features does not improve that.")
    return {"summary": summary, "rows": data}


@tool
def change_data_request(request: Optional[str] = None) -> dict:
    """Call this when the user asks to change, add, delete, remove, rename, update or edit any data or songs.
    Nothing can be changed because this data is read-only. This returns the message to give the user.
    Do NOT use a statistics or search tool for these requests."""
    return {"summary": "REFUSED. This data is read-only, so nothing was changed, added or deleted. Tell the user: "
                       "\"I can only read this data, so I can't do that.\" You can offer to show statistics or look up songs instead.",
            "changed": False}


@tool
def list_values(column: str = "genre") -> dict:
    """column is genre or artist_country. The genres or country codes that exist in the data, with how many songs each has. Use to find the exact name to filter on."""
    return {"column": column, "values": rows(f"SELECT {column} AS value, count() AS songs FROM songs WHERE {column} IS NOT NULL GROUP BY {column} ORDER BY songs DESC LIMIT 40")}


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8001)
