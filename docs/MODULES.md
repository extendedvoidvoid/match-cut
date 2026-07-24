# Modules — experiments as mixable features

Pipeline features (kiss classify, rate, fx, acquire) live under `scripts/modules/`.  
**Mix recipes become new modules** you re-apply to new stills/videos.

## CLI

```bash
mc module list
mc module list --type classify
mc module show classify.kiss_mouth_geo
mc module run select.filter_kiss_geo
mc module run render.flat_rate --set rate=30 --set duration=60
mc module mix select.filter_kiss_geo render.flat_rate fx.negative_toggle --as kiss_flat30_neg
mc module apply mix.kiss_flat30_neg --dry-run
mc module apply mix.kiss_flat30_neg
```

## Types

| Type | Role |
|------|------|
| acquire | READ genre / SEE Qwen / BRUTE download |
| classify | Pass A, mouth geo, Qwen VL |
| select | filter/sort label pools |
| render | stills → reel |
| fx | video → video |
| mix | composed recipe → **new module id** |

## Kiss stack

```
classify.pass_a_faces → classify.kiss_mouth_geo → [classify.kiss_qwen_full]
select.filter_kiss_geo → select.sort_mouth_close → render.flat_rate
```

Default mix: `mix.kiss_flat30_neg` (geo pool + flat 30 + negative toggle).

## Acquire (images) — online meta only

**Online:** title / genre / tags / **TMDB keywords** (IMDb taxonomy proxy). **No vision online**.  
**Local after download:** MediaPipe + mouth geo; Qwen optional post-hoc only.

Principal rank signal = keyword **affinity** (plot_detail / subgenre / …), not a fixed keyword allow-list.  
Doc: `docs/IMDB_KEYWORD_TAXONOMY.md` · config: `config/intent_profiles.json`.

```
acquire.read_genre → acquire.read_tags
  → acquire.fetch_tmdb_keywords
  → acquire.rank_meta (intent=kiss_romance, top K)
  → acquire.brute_download → classify.pass_a_faces → classify.kiss_mouth_geo
```

```bash
mc module run acquire.read_genre
mc module run acquire.read_tags
mc module run acquire.fetch_tmdb_keywords
mc module run acquire.rank_meta --set top_k=20 --set min_score=2 --set intent=kiss_romance
mc module run acquire.brute_download
mc module run classify.kiss_mouth_geo   # or classify-pass-a --regeo
mc module run select.filter_kiss_geo
```

`acquire.see_sample_qwen` = experiment only (not acquire gate).  
Older posts: gallery via `bwg_frontend_data` ajax (`brute_from_see.py` / `kiss_see.py`).

## Rules

1. New experiment = new module + registry entry (`status: experiment`).
2. `mc module mix A B C --as name` writes recipe + registers `mix.name`.
3. Keep-all stills; labels additive.
4. Old CLIs (`mc classify-pass-a`, `mc reel-fx-mix`) still work.
