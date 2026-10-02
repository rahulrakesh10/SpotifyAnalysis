# What makes a song rise?

An analysis of Spotify's 730 most-streamed songs (snapshot July 2026). The question: once you know how long ago a song came out, does anything else predict how fast it is still gaining streams?

## What we found

- **Release age is the main driver.** Newer songs gain streams much faster, and growth drops for about 3 years after release before levelling off. Age alone explains about half the difference between songs, even for artists the model had never seen.
- **Country and Latin music stand out.** Beyond age, these are the only two genres that clearly grow faster: about 52% faster than pop songs of the same age.
- **Most other things don't matter.** How a song sounds (danceability, energy, mood, tempo), explicit lyrics, collaborations, and singles vs album tracks had no reliable effect.

Limits: every song already has 100M+ streams, so this describes hits, not songs in general. It's a single snapshot, not a trend over time.

![Growth vs release age](reports/velocity_vs_age.png)
![Effects beyond release age](reports/effects.png)

Full tables are in [reports/results.md](reports/results.md).

## What we used

**Data**
- The Spotify CSV: total and daily streams for 730 songs.
- Deezer: release date, genre, song length, explicit flag, single or album.
- MusicBrainz: original release date (replaces reissue dates), artist country, solo or group.
- ReccoBeats: audio features (danceability, energy, mood, tempo).

**Tools:** Python, pandas, statsmodels, scikit-learn, matplotlib.

**Method:** Growth speed is today's streams divided by all-time streams. A regression model compares songs of the same age that differ in one way. Songs by the same artist are grouped, results are adjusted for testing many factors at once, and the model is tested on artists it hasn't seen.

## Run it

```bash
python3 enrich.py    # first run takes ~15 min (API rate limits), then it's cached
python3 analyze.py   # runs the model, makes the charts and an interactive dashboard
```

Needs `pandas`, `requests`, `statsmodels`, `scikit-learn`, `matplotlib`. No API keys.

## Files

- `enrich.py`: adds the Deezer, MusicBrainz and ReccoBeats data
- `analyze.py`: the model, charts and dashboard
- `data/`: the original and enriched CSVs
- `reports/`: results table and charts
