# Decision: Keep-all film-grab + gradual classify

**Date:** 2026-07-17  
**Status:** active

## Policy

1. **Never delete** stills for failed face-pass or missing labels.  
2. **Source of truth:** `assets/film-grab/<slug>/*.jpg` + `manifest.jsonl`.  
3. **Labels** live in `classifications.jsonl` (additive merge).  
4. **Film meta** in `films.jsonl` (scaffold now; Firecrawl enrich later).  
5. **Inventory** regenerated with all on-disk rows; preserves `notes` / `marked_delete`.

## Commands

```bash
mc fetch-film-grab audit
mc fetch-film-grab enrich-manifest
mc fetch-film-grab inventory
mc classify-pass-a                 # MediaPipe Pass A (local)
mc classify-pass-a --force         # re-run all
```

## Pass A results (2026-07-17, 4000 stills)

| Label | Count |
|-------|------:|
| total | 4000 |
| zero face | 2931 |
| multi-face (kiss candidates) | 109 |
| thumb source URLs in manifest | 1474 |

Kiss reel at 10→40 / 60s needs ~1500–1950 unique frames — **yield too low**; grow pool + Pass C (LiteLLM VL) on candidates.

## Next

- P2 Firecrawl → fill `post_url` / title / full gallery URLs  
- P3 LiteLLM VL `has_kiss` on multi-face + lips  
- Optional full-res re-fetch for thumb URLs (keep files until replaced)
