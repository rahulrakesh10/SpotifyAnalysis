# What makes a song rise fast?

Songs analysed: 707 (with release date); 621 also have audio features.

Outcome: today's streams as a share of all-time streams, log scale.

## Model comparison

| Model | Songs | R² | Out-of-sample R² (by artist) |
|---|---|---|---|
| age only | 707 | 0.54 | 0.52 |
| age + metadata | 707 | 0.59 | 0.49 |
| age + metadata + audio | 621 | 0.59 | 0.44 |
| age + metadata (audio subset) | 621 | 0.57 | 0.44 |

## Effects in the full model (holding everything else fixed)

| Factor | Effect on growth speed | 95% CI | p | p (adjusted for ~30 tests) |
|---|---|---|---|---|
| Genre: Country | +52% | +24% to +86% | 0.000 | 0.002 |
| Genre: Latin Music | +52% | +21% to +90% | 0.000 | 0.008 |
| Group (vs solo artist) | +18% | +2% to +37% | 0.030 | 0.888 |
| Audio: danceability (+1 SD) | -6% | -11% to -0% | 0.049 | 1.000 |
| Genre: Other | +24% | -0% to +53% | 0.050 | 1.000 |
| Artist from: Canada | +19% | -1% to +44% | 0.062 | 1.000 |
| Length (per extra minute) | +7% | -0% to +15% | 0.066 | 1.000 |
| Genre: Dance | +18% | -5% to +47% | 0.142 | 1.000 |
| Genre: Rap/Hip Hop | +17% | -5% to +45% | 0.144 | 1.000 |
| Artist from: Other | +18% | -7% to +49% | 0.169 | 1.000 |
| Audio: energy (+1 SD) | -4% | -9% to +2% | 0.173 | 1.000 |
| Genre: Brazilian Music | +41% | -15% to +135% | 0.181 | 1.000 |
| Artist from: Brazil | -26% | -53% to +17% | 0.202 | 1.000 |
| Artist from: Unknown | -15% | -35% to +11% | 0.237 | 1.000 |
| Genre: Asian Music | -15% | -37% to +15% | 0.300 | 1.000 |
| Artist from: Latin America (other) | -9% | -25% to +10% | 0.312 | 1.000 |
| Released as: Compilation | -12% | -33% to +15% | 0.345 | 1.000 |
| Audio: speechiness (+1 SD) | -2% | -7% to +2% | 0.354 | 1.000 |
| Genre: Electro | +13% | -17% to +54% | 0.443 | 1.000 |
| Audio: tempo (+1 SD) | +2% | -3% to +7% | 0.479 | 1.000 |
| Genre: Alternative | -9% | -33% to +24% | 0.556 | 1.000 |
| Artist from: UK/Europe | +6% | -13% to +29% | 0.571 | 1.000 |
| Artist's hits in list (×2) | -2% | -8% to +5% | 0.571 | 1.000 |
| Audio: acousticness (+1 SD) | +2% | -4% to +7% | 0.583 | 1.000 |
| Artist from: Asia | +7% | -17% to +39% | 0.595 | 1.000 |
| Collaboration | +15% | -38% to +111% | 0.654 | 1.000 |
| Genre: R&B | -5% | -23% to +19% | 0.668 | 1.000 |
| Audio: valence (+1 SD) | -1% | -6% to +4% | 0.752 | 1.000 |
| Explicit | -2% | -13% to +11% | 0.771 | 1.000 |
| Artist from: Mexico | +3% | -18% to +30% | 0.799 | 1.000 |
| Released as: Single | -1% | -14% to +13% | 0.868 | 1.000 |
| Released as: EP | +1% | -16% to +21% | 0.919 | 1.000 |

## Rising much faster than their age predicts

| track                                           | artist                | original_release_date   | genre           | artist_country   |   vs_expected_pct |
|:------------------------------------------------|:----------------------|:------------------------|:----------------|:-----------------|------------------:|
| Cuando No Era Cantante                          | El Bogueto            | 2024-09-26              | Latin Music     | MX               |               583 |
| Clean Baby Sleep White Noise (Loopable no fade) | Dream Supplier        | 2020-12-07              | Pop             | nan              |               534 |
| Rein Me In                                      | Sam Fender            | 2025-02-21              | Alternative     | GB               |               381 |
| Tus Mentiras (En Vivo)                          | Moy Bobadilla         | 2025-04-10              | Latin Music     | nan              |               339 |
| Dirimu Yang Dulu                                | Anggis Devaki         | 2024-11-29              | Asian Music     | ID               |               323 |
| Sadrah                                          | For Revenge           | 2024-03-18              | Pop             | FI               |               300 |
| Calma                                           | Jorge & Mateus        | 2014-10-21              | Brazilian Music | BR               |               293 |
| Midnight Sun                                    | Zara Larsson          | 2025-06-13              | Pop             | SE               |               258 |
| Everybody Here Wants You                        | Jeff Buckley          | 1998-01-01              | Rock            | US               |               253 |
| So Far So Fake                                  | Pierce The Veil       | 2023-02-10              | Rock            | US               |               249 |
| Arriba la Compañía                              | LOS DOS DE TAMAULIPAS | 2024-06-14              | Latin Music     | US               |               184 |
| Edge of Desire                                  | Jonas Blue            | 2025-07-18              | Electro         | GB               |               179 |

## Fading faster than their age predicts

| track                           | artist              | original_release_date   | genre           | artist_country   |   vs_expected_pct |
|:--------------------------------|:--------------------|:------------------------|:----------------|:-----------------|------------------:|
| MAMA.CITA (hasta la vista)      | Luísa Sonza         | 2022-12-21              | nan             | BR               |               -84 |
| Altas Loucurinhas (Uni Duni Tê) | Matheus Fernandes   | 2023-01-06              | Alternative     | nan              |               -83 |
| CACHORRINHAS                    | Luísa Sonza         | 2022-07-18              | Pop             | BR               |               -80 |
| Wake Up                         | Fetty Wap           | 2016-04-22              | Rap/Hip Hop     | US               |               -79 |
| Balanço da Rede                 | Matheus Fernandes   | 2021-10-01              | Brazilian Music | nan              |               -79 |
| It's Strange                    | Louis The Child     | 2015-10-22              | Electro         | US               |               -78 |
| Beautiful Strangers             | TOMORROW X TOGETHER | 2025-07-21              | Asian Music     | KR               |               -77 |
| The Only Thing                  | Sufjan Stevens      | 2015-03-31              | Alternative     | US               |               -71 |
| Someone That Loves You          | HONNE               | 2016-01-01              | Alternative     | GB               |               -71 |
| Opa cadê eu                     | Clayton & Romário   | 2025-02-06              | Brazilian Music | nan              |               -68 |
| Meant to Be Yours               | Kevin Murphy        | 2025-06-06              | Films/Games     | US               |               -67 |
| Kupu                            | Tiara Andini        | 2024-04-18              | Pop             | ID               |               -66 |
