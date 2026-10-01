"""What makes a song rise fast? Age-controlled analysis of the enriched dataset.

Outcome ("velocity"): daily streams as a share of all-time streams (daily_stream_share_pct),
modelled on the log scale so coefficients read as % differences.

Writes reports/results.md, charts, and reports/dashboard.html (built from dashboard_template.html).
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GroupKFold, cross_val_score
from statsmodels.nonparametric.smoothers_lowess import lowess

ROOT = Path(__file__).parent
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

# Chart tokens (light mode, reference palette)
SURFACE, INK, INK_2, GRID, SERIES = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"

REGIONS = {
    "US": "US", "CA": "Canada", "GB": "UK/Europe", "FR": "UK/Europe", "SE": "UK/Europe", "DE": "UK/Europe",
    "IT": "UK/Europe", "ES": "UK/Europe", "NL": "UK/Europe", "IE": "UK/Europe", "NO": "UK/Europe",
    "MX": "Mexico", "BR": "Brazil", "PR": "Latin America (other)", "CO": "Latin America (other)",
    "AR": "Latin America (other)", "CL": "Latin America (other)", "DO": "Latin America (other)",
    "EC": "Latin America (other)", "VE": "Latin America (other)", "PE": "Latin America (other)",
    "KR": "Asia", "JP": "Asia", "IN": "Asia", "ID": "Asia", "PH": "Asia", "CN": "Asia", "TH": "Asia",
}
AUDIO = ["danceability", "energy", "valence", "acousticness", "speechiness", "tempo"]


def load():
    df = pd.read_csv(ROOT / "data" / "spotify_2025_enriched.csv")
    # Need a release date (for age) and a Deezer match (for length, format, explicit)
    df = df[(df["days_since_release"] > 0) & df["duration_sec"].notna()].copy()
    df["log_velocity"] = np.log(df["daily_stream_share_pct"])
    df["log_age"] = np.log(df["days_since_release"])
    top_genres = df["genre"].value_counts()
    df["genre_g"] = df["genre"].where(df["genre"].map(top_genres) >= 20, "Other").fillna("Unknown")
    df["region"] = df["artist_country"].map(REGIONS).fillna(
        pd.Series(np.where(df["artist_country"].isna(), "Unknown", "Other"), index=df.index)
    )
    df["album_type"] = df["album_type"].fillna("unknown")
    df["explicit"] = df["explicit"].fillna(False).astype(int)
    df["collab"] = df["is_collaboration"].astype(int)
    df["is_group"] = (df["artist_type"] == "Group").astype(int)
    df["duration_min"] = df["duration_sec"] / 60
    df["artist_songs_in_list"] = df.groupby("artist")["track"].transform("size")
    df["log_artist_songs"] = np.log(df["artist_songs_in_list"])
    for f in AUDIO:
        col = df[f"af_{f}"]
        df[f"z_{f}"] = (col - col.mean()) / col.std()
    return df


FORMULAS = {
    # Growth falls steeply for ~3 years then flattens, so age enters as a spline, not a straight line
    "age only": "log_velocity ~ bs(log_age, df=4)",
    "age + metadata": (
        "log_velocity ~ bs(log_age, df=4) + C(genre_g, Treatment('Pop')) + C(region, Treatment('US'))"
        " + C(album_type, Treatment('album')) + explicit + collab + is_group + duration_min + log_artist_songs"
    ),
}
FORMULAS["age + metadata + audio"] = FORMULAS["age + metadata"] + "".join(f" + z_{f}" for f in AUDIO)


def fit(df, formula):
    # Standard errors clustered by artist: Bad Bunny's 15 songs are not 15 independent observations
    return smf.ols(formula, data=df).fit(cov_type="cluster", cov_kwds={"groups": df["artist"]})


def cv_r2(df, formula):
    """Out-of-sample R², folds grouped by artist so an artist is never in both train and test."""
    import patsy

    y, X = patsy.dmatrices(formula, df, return_type="dataframe")
    groups = df.loc[y.index, "artist"]
    return cross_val_score(LinearRegression(), X, y.values.ravel(), groups=groups,
                           cv=GroupKFold(5), scoring="r2").mean()


def pretty(term):
    term = term.replace("C(genre_g, Treatment('Pop'))[T.", "Genre: ").replace("C(region, Treatment('US'))[T.", "Artist from: ")
    term = term.replace("C(album_type, Treatment('album'))[T.", "Released as: ").rstrip("]")
    term = term.replace("as: ep", "as: EP").replace("as: single", "as: Single").replace("as: compile", "as: Compilation")
    return {
        "log_age": "Release age (per doubling)", "explicit": "Explicit", "collab": "Collaboration",
        "is_group": "Group (vs solo artist)", "duration_min": "Length (per extra minute)",
        "log_artist_songs": "Artist's hits in list (×2)",
    }.get(term, f"Audio: {term[2:]} (+1 SD)" if term.startswith("z_") else term)


def effects_table(model):
    rows = []
    for term in model.params.index.drop("Intercept"):
        if term.startswith("bs(log_age"):
            continue  # spline pieces aren't individually interpretable; see velocity_vs_age.png
        b, (lo, hi), p = model.params[term], model.conf_int().loc[term], model.pvalues[term]
        scale = np.log(2) if term == "log_artist_songs" else 1.0  # per doubling
        rows.append({
            "term": pretty(term), "effect_pct": (np.exp(b * scale) - 1) * 100,
            "lo_pct": (np.exp(lo * scale) - 1) * 100, "hi_pct": (np.exp(hi * scale) - 1) * 100, "p": p,
        })
    eff = pd.DataFrame(rows)
    # ~30 factors are tested at once, so some p < 0.05 results are expected by chance. Holm corrects for that.
    eff["p_adj"] = multipletests(eff["p"], method="holm")[1]
    return eff


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.xaxis.label.set_color(INK_2)
    ax.yaxis.label.set_color(INK_2)


def chart_age(df):
    fig, ax = plt.subplots(figsize=(8, 5), facecolor=SURFACE)
    style(ax)
    ax.grid(True, color=GRID, linewidth=0.6, zorder=0)
    ax.scatter(df["days_since_release"], df["daily_stream_share_pct"], s=18, color=SERIES, alpha=0.45,
               edgecolor=SURFACE, linewidth=0.6, zorder=2)
    trend = lowess(df["log_velocity"], df["log_age"], frac=0.4)
    ax.plot(np.exp(trend[:, 0]), np.exp(trend[:, 1]), color=INK, linewidth=2, zorder=3)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ticks = [30, 90, 180, 365, 730, 1825, 3650]
    ax.set_xticks(ticks, ["1 mo", "3 mo", "6 mo", "1 yr", "2 yr", "5 yr", "10 yr"])
    ax.set_xlabel("Time since release (log scale)")
    ax.set_ylabel("Today's streams as % of all-time streams (log)")
    ax.set_title("Newer songs grow faster: one song per dot, black line = trend", loc="left", color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(REPORTS / "velocity_vs_age.png", dpi=160)
    plt.close(fig)


def chart_effects(eff):
    eff = eff.sort_values("effect_pct")
    fig, ax = plt.subplots(figsize=(8, 0.32 * len(eff) + 1.2), facecolor=SURFACE)
    style(ax)
    ax.axvline(0, color=INK_2, linewidth=1)
    y = np.arange(len(eff))
    ax.hlines(y, eff["lo_pct"], eff["hi_pct"], color=SERIES, linewidth=2)
    sig = eff["p_adj"] < 0.05
    # Filled = clear after adjusting for testing many factors; hollow = could be noise. Shape, not just color.
    ax.scatter(eff["effect_pct"][sig], y[sig], s=64, color=SERIES, edgecolor=SERIES, linewidth=2, zorder=3)
    ax.scatter(eff["effect_pct"][~sig], y[~sig], s=48, facecolor=SURFACE, edgecolor=SERIES, linewidth=2, zorder=3)
    ax.set_yticks(y, eff["term"], fontsize=9, color=INK)
    ax.set_xlabel("% difference in growth speed, holding release age and everything else fixed")
    ax.set_title("What predicts faster growth once release age is accounted for\n"
                 "Filled = clear even after adjusting for ~30 tests · hollow = could be noise · bar = 95% range",
                 loc="left", color=INK, fontsize=11)
    ax.grid(True, axis="x", color=GRID, linewidth=0.6)
    fig.tight_layout()
    fig.savefig(REPORTS / "effects.png", dpi=160)
    plt.close(fig)


def main():
    df = load()
    audio_df = df.dropna(subset=[f"z_{f}" for f in AUDIO])

    out = ["# What makes a song rise fast?\n",
           f"Songs analysed: {len(df)} (with release date); {len(audio_df)} also have audio features.\n",
           "Outcome: today's streams as a share of all-time streams, log scale.\n",
           "## Model comparison\n", "| Model | Songs | R² | Out-of-sample R² (by artist) |", "|---|---|---|---|"]
    models, model_rows = {}, []
    runs = [(name, formula, audio_df if "audio" in name else df) for name, formula in FORMULAS.items()]
    # Same songs for a fair audio vs no-audio comparison
    runs.append(("age + metadata (audio subset)", FORMULAS["age + metadata"], audio_df))
    for name, formula, data in runs:
        m = fit(data, formula)
        models.setdefault(name, m)
        row = {"model": name, "n": len(data), "r2": round(m.rsquared, 3), "cv_r2": round(cv_r2(data, formula), 3)}
        model_rows.append(row)
        out.append(f"| {name} | {row['n']} | {row['r2']:.2f} | {row['cv_r2']:.2f} |")

    final = models["age + metadata + audio"]
    eff = effects_table(final)
    out += ["\n## Effects in the full model (holding everything else fixed)\n",
            "| Factor | Effect on growth speed | 95% CI | p | p (adjusted for ~30 tests) |", "|---|---|---|---|---|"]
    for r in eff.sort_values("p").itertuples():
        out.append(f"| {r.term} | {r.effect_pct:+.0f}% | {r.lo_pct:+.0f}% to {r.hi_pct:+.0f}% | {r.p:.3f} | {r.p_adj:.3f} |")

    # Songs rising faster / slower than their age alone predicts
    age_model = models["age only"]
    df["resid"] = age_model.resid
    df["vs_expected_pct"] = (np.exp(df["resid"]) - 1) * 100
    cols = ["track", "artist", "original_release_date", "genre", "artist_country", "vs_expected_pct"]
    for title, part in (("Rising much faster than their age predicts", df.nlargest(12, "resid")),
                        ("Fading faster than their age predicts", df.nsmallest(12, "resid"))):
        out += [f"\n## {title}\n", part[cols].round(0).to_markdown(index=False)]

    (REPORTS / "results.md").write_text("\n".join(out) + "\n")
    df.to_csv(REPORTS / "songs_with_residuals.csv", index=False)
    chart_age(df)
    chart_effects(eff)
    build_dashboard(df, eff, model_rows, age_model)
    print("\n".join(out))


def build_dashboard(df, eff, model_rows, age_model):
    # Only draw the expected pace where there is data to support it (few songs are under ~5 months old)
    grid = np.linspace(df["log_age"].quantile(0.02), df["log_age"].quantile(0.995), 80)
    curve = np.exp(age_model.predict(pd.DataFrame({"log_age": grid})))
    clean = lambda v: None if pd.isna(v) else v
    songs = [{
        "t": r.track, "a": r.artist, "g": clean(r.genre), "c": clean(r.artist_country),
        "d": str(r.original_release_date), "src": r.date_source, "age": int(r.days_since_release),
        "v": round(r.daily_stream_share_pct, 4), "x": round(r.vs_expected_pct, 1),
        "s": int(r.spotify_streams_total), "ds": int(r.daily_streams), "rank": int(r.rank),
    } for r in df.itertuples()]
    group = lambda t: t.split(":")[0] if ":" in t else "Song & artist"
    effects = [{
        "term": r.term.split(": ", 1)[-1], "group": group(r.term), "e": round(r.effect_pct, 1),
        "lo": round(r.lo_pct, 1), "hi": round(r.hi_pct, 1), "p": round(r.p, 4), "padj": round(r.p_adj, 4),
    } for r in eff.itertuples()]
    data = {
        "songs": songs, "effects": effects, "models": model_rows,
        "curve": [[round(float(np.exp(g)), 1), round(float(c), 4)] for g, c in zip(grid, curve)],
        "dates_fixed": int((df["date_source"] == "musicbrainz").sum()),
    }
    html = (ROOT / "dashboard_template.html").read_text()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    (REPORTS / "dashboard.html").write_text(html.replace("__DATA__", payload))


if __name__ == "__main__":
    main()
