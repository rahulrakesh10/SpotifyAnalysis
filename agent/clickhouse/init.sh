#!/bin/bash
# Runs once, the first time the ClickHouse container starts with an empty data volume.
set -euo pipefail
cp /seed/spotify_2025_enriched.csv /var/lib/clickhouse/user_files/songs.csv
cp /seed/model_effects.csv /seed/model_comparison.csv /seed/song_growth.csv /var/lib/clickhouse/user_files/
clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --multiquery <<SQL
CREATE TABLE spotify.songs
ENGINE = MergeTree ORDER BY tuple()
AS SELECT s.*, g.expected_growth_pct AS expected_growth_pct, g.vs_expected_pct AS vs_expected_pct
FROM (
    SELECT * REPLACE (
        toDate32(original_release_date) AS original_release_date,
        toDate32(release_date) AS release_date,
        explicit = 'True' AS explicit,
        is_collaboration = 'True' AS is_collaboration,
        toFloat64OrNull(af_valence) AS af_valence,
        toFloat64OrNull(af_acousticness) AS af_acousticness,
        toFloat64OrNull(af_instrumentalness) AS af_instrumentalness,
        toInt32(release_year) AS release_year,
        toInt32(days_since_release) AS days_since_release
    ) FROM file('songs.csv', 'CSVWithNames')
) AS s
-- growth vs what is typical for the song's age; blank (NULL) for the songs the model could not cover
LEFT JOIN (SELECT rank, expected_growth_pct, vs_expected_pct FROM file('song_growth.csv', 'CSVWithNames')) AS g
    ON s.rank = g.rank
SETTINGS schema_inference_make_columns_nullable = 1, join_use_nulls = 1;

-- Results of the regression analysis (analyze.py)
CREATE TABLE spotify.model_effects ENGINE = MergeTree ORDER BY tuple()
AS SELECT * FROM file('model_effects.csv', 'CSVWithNames');

CREATE TABLE spotify.model_comparison ENGINE = MergeTree ORDER BY tuple()
AS SELECT * FROM file('model_comparison.csv', 'CSVWithNames');

-- The agent's login can only read the spotify database. It cannot write, alter or drop anything.
CREATE USER agent_ro IDENTIFIED WITH sha256_password BY '${AGENT_RO_PASSWORD}';
GRANT SELECT ON spotify.* TO agent_ro;
SQL
