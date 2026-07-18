# Where is what? (human map)

Plain English map for César. Branch: `feat/fashion-essay-vertical`.

---

## 1) The website you like (browser)

**Project folder:**  
`/Users/alexphoenix/projects/match-cut`

| What you see | Where it lives on disk |
|--------------|------------------------|
| Main tool page | `app/page.tsx` |
| About / marketing layout | `app/about/page.tsx` |
| Shared chrome / fonts | `app/layout.tsx` · `app/globals.css` |
| Buttons, upload, preview UI | `components/` |
| Demo video file(s) in the site | `public/` (today e.g. `effect demo.mp4`) |
| Run the site | `mc dev` → usually http://localhost:3000 |

**We will not erase this.** Vertical work is a **separate offline tool**.  
If we ever redesign the site: **version first** (git branch or tag) so you can reuse the template on another project.

---

## 2) Upload every time (light collab)

| File | What it is |
|------|------------|
| **`docs/history/COLLAB_HANDOFF.md`** | **Upload this every session** — short recap + Grok↔Opus summaries only. Grok updates it. |

## 3) The Opus / full-spec docs (do not dump into handoff)

Not a chat export. Long truth lives here:

| File | What it is |
|------|------------|
| **`docs/history/VERTICAL_V1_SPEC.md`** | Main decisions + Opus Option 1 + filter lock |
| **`docs/ROADMAP_VIDEO_ESSAY_APP.md`** | Later: leave match-cut → own video-essay / VJ app |
| **`tools/vertical/ARCHITECTURE.md`** | Pass A — modules, YAML, ffmpeg (no impl yet) |
| **`tools/vertical/config.example.yaml`** | Config example |

**Full paths:**

```text
/Users/alexphoenix/projects/match-cut/docs/history/COLLAB_HANDOFF.md   ← upload every time
/Users/alexphoenix/projects/match-cut/docs/history/VERTICAL_V1_SPEC.md
/Users/alexphoenix/projects/match-cut/docs/history/WHERE_IS_WHAT.md   ← this map
/Users/alexphoenix/projects/match-cut/docs/ROADMAP_VIDEO_ESSAY_APP.md
/Users/alexphoenix/projects/match-cut/tools/vertical/ARCHITECTURE.md
```

**Hand to Opus:** upload `COLLAB_HANDOFF.md`; if they need depth, also `ARCHITECTURE.md` + `VERTICAL_V1_SPEC.md`.

---

## 4) Vertical reframe code (not the website)

```text
/Users/alexphoenix/projects/match-cut/tools/vertical/
```

Pass A = design only. Pass B (later) = real Python CLI.  
Does **not** replace `app/` or `public/`.

---

## 5) Album cover essay (other project — keep coherent later)

```text
/Users/alexphoenix/projects/album-video-creator
```

Music / animated cover essays. Fashion essay is the sibling story, not a wipe of match-cut’s site.

---

## 6) Status

- Pass A: confirmed · Pass B: **implemented** · smoke OK  
- Website: **protected** (untouched)  
- Handoff: `docs/history/COLLAB_HANDOFF.md`  
- Run: `cd tools/vertical && PYTHONPATH=. python3 -m vertical_reframe …`
