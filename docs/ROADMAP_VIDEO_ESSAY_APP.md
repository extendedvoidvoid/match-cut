# Roadmap — vertical / fashion essay off match-cut

**Private.** Names TBD by César. No public branding in this file beyond function words.

## Intent

`feat/fashion-essay-vertical` is an **incubator**, not permanent second product inside match-cut forever.

**Separate lanes** (see `docs/history/LANES.md`):

- **VJ** = ~1 min reels / montages (`exports/reels`) — experimentation; **not** Station F spine.  
- **Essay** = show/collection (e.g. Chanel) landscape → 9:16 + album-cover essay family (`album-video-creator`).  
- film-grab stays acquire for stills; do not equate film-grab reels with Station F.

Vertical reframe + fashion **essay** packaging should **migrate** to their own **video-essay app** when green.  
VJ may migrate separately (or stay match-cut) — **do not force one app for both.**

## Phases

### NOW (this branch)

```text
match-cut monorepo
  ├── client photo match-cut          # sacred — do not break export contract
  ├── film-grab / classify / reels    # stay; do not reimplement as reframe
  └── tools/vertical/                 # temporary home for center_crop v1
```

### NEXT (core green)

```text
new repo or extract (name TBD by César)
  ├── vertical reframe CLI (this v1 matured)
  ├── fashion essay pack (coherent with César+ album essay defaults)
  └── optional VJ modules later
```

Exit criteria to migrate:

- center_crop DoD green on real landscape show/collection clips  
- One documented smoke path César trusts  
- No dependency on Next app for reframe  
- Spec still points at album-essay coherence (9:16 grammar)

### LATER

- film-grab acquire as **shared lib/submodule** if needed — **do not** copy 8k stills into essay app  
- `smart_subject` as **Python module** (not browser): `SubjectDetector` + EMA/one-euro; **default RF-DETR core (Apache 2.0)** / RTMDet; YOLO26 AGPL only if César Accepts; reuse classify.*  
- Tracking: ByteTrack-class default; **SAM 3.1** (Object Multiplex) occlusion escalation, not default  
- Browser MediaPipe stays **photo match-cut only** — do not dual-maintain heavy detectors in wasm  
- Optional **local** VLM on M3 for uncertain frames — never cloud vision / never required for reframe  
- Optional Mistral for **copy** only — never required for offline reframe

## Anti-redundancy

| Do | Do not |
|----|--------|
| One reframe home | Python + wasm + Next all reframe |
| Backlog smart_subject | Fake Premiere in v1 |
| Shared encode defaults with César+ later | Random third export naming scheme |
| Roadmap doc updates | New experimental tree every week |

## Relation to album cover essay

`~/projects/album-video-creator` = music / animated cover essay spine.  
Fashion essay = fashion show spine.  
Same Paris cultural density; different assets. Align export defaults over time so a future brand pack is one family.
