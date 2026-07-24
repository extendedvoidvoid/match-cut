# IMDb-style keyword taxonomy (principal meta fallback)

Source: [IMDb Keywords contribution guide](https://help.imdb.com/article/contribution/titles/keywords/GXQ22G5Y72TH8MJ5) (updated 2026-06-29).  
Runtime source for this repo: **TMDB** `GET /movie/{id}/keywords` (free IMDb dumps lack keyword TSV). Categories are **inferred** to mirror IMDb structure — TMDB returns flat `{id,name}` only.

## Why

Film-grab genre/tags are sparse. Per-title keywords (`castle`, `house`, `couple`, `kiss`, `the devil`, …) are a dense plot/visual index. Use them as **principal** rank signal before download/vision — never a fixed global allow-list of “good” words.

## IMDb categories (canonical)

| Category | Role | Examples | Scoring bias (visual stills) |
|----------|------|----------|------------------------------|
| **plot_detail** | Notable object / concept / action | kiss, castle, baby, stampede, married-couple | **High** — still content |
| **subgenre** | Meaningful sub-genre of whole title | feel-good-romance, dark-comedy, jungle-adventure | **Medium** — intent lane |
| **timeframe** | When plot is set | 1960s, world-war-two, victorian-era | **Low–medium** — filter only |
| **franchise** | Preset franchise IP tags | star-wars, marvel, james-bond | **Low** — cluster, not emotion |
| **other** | Residual / display / meta | f-rated, based-on-novel, *-character | **Lowest** |

Rules from IMDb (useful for annotation quality):

- Keywords: lower-case; contribute with dashes; display with spaces.
- Plot details: open-ended; singular English; no title repeat; no raw genres; no production companies.
- Subgenre must matter for the **whole** title (not one scene).
- Same keyword can be subgenre on title A and plot_detail on title B; on one title, subgenre wins over plot_detail.

## Useful vs absurd (for rank)

| Useful for kiss / establishing stills | Usually noise for our pools |
|--------------------------------------|-----------------------------|
| plot_detail affinity to intent seeds | franchise-only hits |
| subgenre affinity (`*-romance`, tragic-romance) | pure meta (`based on novel or book`) |
| rare DF keywords (idf) | ultra-common tags alone |
| film-grab tags as soft seeds | demote seeds from intent profile |

**Never require** a fixed global allow-list. Affinity = token/substring overlap with **intent profile seeds** + category weight + corpus IDF.

## Pipeline (this repo)

```
acquire.read_genre + acquire.read_tags
  → acquire.fetch_tmdb_keywords   # cache keywords_index.jsonl
  → acquire.rank_meta             # principal = keyword affinity (v2)
  → acquire.brute_download
  → classify.*
```

Files:

| Path | Role |
|------|------|
| `config/intent_profiles.json` | Seeds + category weights (per intent) |
| `scripts/fetch-film-grab/kw_taxonomy.py` | Normalize + category annotate + affinity |
| `scripts/fetch-film-grab/fetch_tmdb_keywords.py` | Search TMDB + `/keywords` + cache |
| `scripts/fetch-film-grab/rank_meta.py` | Merge meta + affinity → brute queue |
| `assets/film-grab/keywords/*.json` | Per-slug cache |
| `assets/film-grab/keywords_index.jsonl` | Flat index + DF |

## Optional licensed IMDb path

If Amazon/IMDb licensed keyword dump appears later: same categories, skip heuristic annotator, keep scoring. Free subsets do **not** ship keyword files.

## Intent switch

Default intent `kiss_romance`. Change:

```bash
mc module run acquire.rank_meta --set intent=empty_nature
# or
python3 scripts/fetch-film-grab/rank_meta.py --intent empty_city
```

New intents = new profile in `config/intent_profiles.json` only — no code allow-list.
