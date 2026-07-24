# STATUS — match-cut

**Last updated:** 2026-07-18  
**Intent:** kiss_romance · 1 kiss : 2 empty (nature+city) · crescendo reel  
**Agent rule:** read this file **first** on reopen, then `docs/IMDB_KEYWORD_TAXONOMY.md` if ranking.

---

## Shipped

### Pipeline / modules
- [x] Module registry + `mc module run` (`scripts/modules/registry.json`)
- [x] Acquire READ: genre (`discover_genre`) + tags (`read_tags`)
- [x] Acquire rank v1 → **v2 keyword affinity** (`rank_meta.py`)
- [x] **TMDB keywords** principal meta fallback (`fetch_tmdb_keywords.py`, `kw_taxonomy.py`)
- [x] Intent profiles (no global KW allow-list) — `config/intent_profiles.json`
- [x] Taxonomy doc — `docs/IMDB_KEYWORD_TAXONOMY.md`
- [x] Brute download from film-grab (`brute_from_see.py`)
- [x] Classify Pass A faces + mouth **kiss_geo** (`classify_pass_a`)
- [x] Scene empty via local Qwen VL (`scene_empty` / numbers on disk)
- [x] Units 1k2e + nature/city empty pair (`select.units_1k2e`)
- [x] Render 1k2e crescendo 60s (`render_units_1k2e` path)
- [x] Reel **013** — `exports/reels/013_insta_reel_kiss_1k2e_crescendo_60s.mp4`
- [x] FX experiments (negative toggle, smudge) as mix modules

### Data (approx, this folder)
| Asset | Count / note |
|-------|----------------|
| Film dirs with stills | ~219 |
| JPGs on disk | ~13.5k |
| `classifications.jsonl` | ~11.6k rows |
| Labels `kiss_geo` | ~3843 (raw label presence) |
| `pools/pool_kiss_geo.jsonl` | **29** (filtered τ pool for units) |
| `pools/units_1k2e.jsonl` | **44** units (cycled for 013) |
| Empty labeled scene_type | nature ~909 · city ~878 · interior ~2462 (partial empty set) |
| Keyword cache (not-on-disk pilot) | **253** JSON · **239** with KWs · 1836 unique norms |
| `candidates_brute.jsonl` | **25** ranked (intent `kiss_romance`) |

### Top brute queue (keyword affinity v2)
1. american-beauty  
2. the-piano  
3. stealing-beauty  
4. brokeback-mountain  
5. natural-born-killers  
… see `assets/film-grab/candidates_brute.jsonl`

---

## In progress

- [ ] **Grow kiss_geo unique stills** — bottleneck for unique 60s (need ≫44 without cycle)
- [ ] **Brute top-K** from current `candidates_brute.jsonl` then re-classify geo
- [ ] **Scene empty residual** — unlabeled empties still large (~4k+ in last numbers snapshot)
- [ ] Keyword cache **on-disk titles** (only not-on-disk fetched so far)

---

## Left to ship

### Near-term (kiss reel quality)
- [ ] `acquire.brute_download` on ranked 25+
- [ ] Re-run `classify.pass_a` / kiss_mouth_geo on new stills
- [ ] Rebuild `pool_kiss_geo` + `units_1k2e` with more unique units
- [ ] Re-render 60s **unique-heavy** (less unit cycle than 013)
- [ ] Optional: finish remaining `scene_empty` for better nature/city balance

### Meta / rank polish
- [ ] Fetch TMDB keywords for **on-disk** slugs (better re-rank + audits)
- [ ] Optional licensed IMDb keyword path (free dumps still no KW TSV)
- [ ] Intent profiles for pure empty lanes already stubbed (`empty_nature`, `empty_city`) — pilot rank only

### Product / later
- [ ] Video-essay app roadmap items — `docs/ROADMAP_VIDEO_ESSAY_APP.md` (separate track)
- [ ] Posters / other reel recipes beyond kiss 1k2e

---

## Next command (pick one)

```bash
# 1) Grow stills from keyword-ranked queue (recommended)
mc module run acquire.brute_download
# or:
python3 scripts/fetch-film-grab/brute_from_see.py

# 2) Refresh keyword rank after more tags/genres
mc module run acquire.fetch_tmdb_keywords
mc module run acquire.rank_meta --set top_k=30 --set intent=kiss_romance

# 3) After new downloads — classify + units + render
mc module run classify.kiss_mouth_geo
mc module run select.units_1k2e
# then render path used for 013
```

---

## Do not redo (unless broken)

- Full Pass C online vision as **acquire gate** (policy: online = meta only)
- Hardcoded global keyword allow-list (use intent seeds + category affinity)
- Safari / WebKit browser stack (Playwright Chromium default)

---

## Key paths

| What | Where |
|------|--------|
| This status | `STATUS.md` |
| Modules help | `docs/MODULES.md` |
| Keyword taxonomy | `docs/IMDB_KEYWORD_TAXONOMY.md` |
| Intent seeds | `config/intent_profiles.json` |
| Stills + meta | `assets/film-grab/` |
| Keyword cache | `assets/film-grab/keywords/` |
| Pools / units | `assets/film-grab/pools/` |
| Reels | `exports/reels/` |
| Registry | `scripts/modules/registry.json` |

---

## Update ritual

After a meaningful ship chunk: edit **Shipped / In progress / Left / Next command** and bump **Last updated**. Keep ≤1 screen of signal; details stay in docs + JSONL.
