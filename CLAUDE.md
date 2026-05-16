# CLAUDE.md — Animate CC Pipeline

**For Claude Code on any device opening this repo: read this file FIRST,
then `docs/PLAN.md`, then run `git log --oneline -20`. Those three give
you the full state of the project.**

## What this project is

A production pipeline that takes **rough animatic MP4 shots** (Indian
2D-cartoon style — TMKOC-flavored sketches with timing already worked out
by the client) and produces **clean, reference-accurate 2D animation**
suitable for daily-strip TV production.

The pipeline is built around three insights:

1. **The rough animatic IS the timing template.** We don't regenerate
   motion — we transfer the rough's exact motion onto clean rigged
   characters frame-by-frame.
2. **Claude + a custom MCP server drives Adobe Animate CC** to do the
   mechanical animator work (open doc, import rig, place at bbox, set
   bone angles, insert keyframes, tween, lipsync, render). The animator
   only reviews and fixes the 10-20% Claude can't get right.
3. **Rigs are pre-built by a human rigger** following a strict contract
   (`docs/RIG_SPEC_v1.md`). The rig contract is what makes Claude's
   orchestration possible — every character's bones, layers, and
   switch states have the same names.

Net effect target: ~₹50K-1.5L per 22-min episode (vs ₹40-70 lakh
traditional 2D animation), 8-12 person team (vs 40-50), 3-5 days
turnaround (vs 4-6 weeks).

## Relationship to the prior project (`animatic-refinement`)

The sibling repo `animatic-refinement` (Part 1 + Part 2 AI-generation
pipeline, 11 nodes with Flux/ControlNet/IP-Adapter/LoRAs) is the
PRECURSOR to this one. It solved Nodes 1-5 (input form, queue, MP4
decode, keypose extraction, character detection) which we **reuse here
in spirit**. Its Node 7 Flux generation path proved that AI image
generation gets ~70-80% character identity — not good enough for
production daily-strip output.

This repo abandons AI image generation in favor of **rigged 2D
characters orchestrated by Claude in Animate CC**. The bbox detection +
positional identity assignment + keypose extraction logic from the
prior repo informs our pipeline; the code itself is re-implemented
fresh here so the new repo is self-contained.

## Build method — IMPORTANT, do not deviate

We build **one phase at a time**. Each phase is the smallest commit
that lands a working, tested chunk. The phases are listed in
`docs/PHASE_3_ROADMAP.md` (3a → 3p; this commit ships 3a).

For every phase:
1. **Discuss + lock** the decisions for this phase. Add to the
   "locked decisions" section of CLAUDE.md.
2. **Update canonical files in sync** (see "Per-phase ship checklist"
   below). All six canonical files must reflect the same state of the
   world before commit.
3. **Write the code** (or scaffolding for that phase).
4. **Add tests** that prove the phase works.
5. **Run tests** + drift-grep + manual smoke if applicable.
6. **Commit** with the canonical message format.
7. **Push** session branch fast-forward to `origin/main`.
8. **Tell the operator**: "Run `git pull` in your main working copy to sync."

Never skip ahead. Never bundle two phases into one commit. Never let
canonical files drift out of sync.

## Per-phase ship checklist — run through BEFORE the commit

- [ ] All tests pass (`pytest -x` or per-phase smoke script)
- [ ] Canonical files in sync (six files below)
- [ ] Drift-grep clean: no references to phases-not-yet-shipped marked
      as "DONE"; no references to old behavior the phase replaces
- [ ] `requirements.txt` reflects any new Python deps
- [ ] `.claude/settings.json` reflects any new MCP servers / env vars
- [ ] Status table in CLAUDE.md updated (phase moves from pending → done)
- [ ] Locked-decisions section appended if new decisions made
- [ ] Phase entry in `docs/PHASE_3_ROADMAP.md` updated with ship date +
      brief notes on what shipped
- [ ] `git status` shows only intended files; **no `git add -A`**
      (secrets risk — stage by name only)
- [ ] Commit message follows format below
- [ ] After push: "Run `git pull` in your main working copy to sync."

## The six canonical files (must stay in sync)

1. `CLAUDE.md` — this file. Project context, locked decisions,
   status table, environment gotchas, pickup instructions.
2. `README.md` — human-facing overview, quick-start, links into docs.
3. `docs/PLAN.md` — full architecture description (what each piece
   does and how they fit together).
4. `docs/PHASE_3_ROADMAP.md` — phase-by-phase ship plan with status.
5. **Subsystem READMEs** — `animate_cc_pipeline/README.md`,
   `animate_cc_pipeline/mcp_server/README.md`, `rigs/README.md`.
6. `requirements.txt` — exact Python dep pins.

Plus `docs/RIG_SPEC_v1.md` for rig contract (separate canonical, not
in the "six" but equally locked).

## Commit message format

- New phase: `Implement Phase 3<letter>: <name>` (e.g.,
  `Implement Phase 3a: project scaffold + 13 locked decisions`)
- Bug fix: `fix: <short description>`
- Tooling / canonical reconciliation: `chore: <short description>`
- Always end with the Co-Authored-By trailer:

```
Co-Authored-By: Claude <noreply@anthropic.com>
```

## Repo map

```
animate-cc-pipeline/
├── CLAUDE.md                       ← you are here
├── README.md                        ← human-facing entrypoint
├── requirements.txt                 ← Python deps
├── .gitignore
├── .claude/
│   └── settings.json                ← Claude Code config + MCP registration
├── docs/
│   ├── PLAN.md                      ← architecture
│   ├── PHASE_3_ROADMAP.md           ← phase-by-phase ship plan
│   └── RIG_SPEC_v1.md               ← rig contract (locked)
├── animate_cc_pipeline/
│   ├── README.md                    ← subsystem overview
│   ├── mcp_server/
│   │   ├── README.md                ← MCP server docs
│   │   ├── server.py                ← (Phase 3b) MCP protocol handler
│   │   ├── jsfl_bridge.py           ← (Phase 3b) Animate.exe runner
│   │   ├── tools/                   ← one file per tool category
│   │   │   ├── document.py          ← (Phase 3c)
│   │   │   ├── symbol.py            ← (Phase 3d)
│   │   │   ├── keyframe.py          ← (Phase 3e)
│   │   │   ├── bone.py              ← (Phase 3f)
│   │   │   ├── tween.py             ← (Phase 3g)
│   │   │   ├── audio.py             ← (Phase 3h)
│   │   │   ├── camera.py            ← (Phase 3i)
│   │   │   └── render.py            ← (Phase 3i)
│   │   └── jsfl_templates/          ← parameterized .jsfl scripts
│   ├── orchestrator/
│   │   ├── cli_node6_pose.py        ← (Phase 3j) pose estimation node
│   │   ├── cli_node7_animate.py     ← (Phase 3l) main orchestrator
│   │   ├── pose_to_bones.py         ← (Phase 3k) joint→bone math
│   │   └── shot_processor.py        ← (Phase 3l) per-shot driver
│   ├── rig_contracts/
│   │   └── rig_validator.py         ← (Phase 3f) checks .fla vs spec
│   └── tests/
│       ├── test_mcp_server.py
│       ├── test_pose_to_bones.py
│       └── _smoke_animate_cc.py
├── rigs/
│   ├── README.md
│   ├── _template/
│   │   └── template_character.fla   ← (Phase 3f) placeholder rig
│   └── <character>.fla              ← (Phase 3o) production rigs
├── backgrounds/                     ← location plate PNGs
└── tools/
    └── phase3/
        ├── install_animate_mcp.py   ← registers MCP server
        └── validate_phase3_env.py   ← env check (Animate path, Python, deps)
```

## Current status (update at end of each phase)

| Phase | Title | Status |
|-------|-------|--------|
| 3a | Project scaffold + canonical files + 13 locked decisions | **Shipped 2026-05-14** (commit `0440c04`) |
| 3b | MCP server scaffold + hello-world JSFL | **Shipped 2026-05-14** (commit `33aeb49`) + **fixup-1 2026-05-15** (commit `1b1660b`) |
| 3c | Document tools (create / save / close / import image / import video) | **Shipped 2026-05-16** (commit `680b6f3`) |
| 3d | Symbol placement tools | **Shipped 2026-05-16** (commit `a2df524`) |
| 3e | Keyframe tools | **In progress (this commit)** — 3 of 4 tools verified end-to-end; `remove_keyframe` shipped with known Animate 2020 limitation |
| 3f | Bone tools + rig contract validator + template rig | pending |
| 3g | Tween tools | pending |
| 3h | Audio + lipsync tools | pending |
| 3i | Camera + render tools | pending |
| 3j | Per-frame pose estimation (Node 6) | pending |
| 3k | Pose → bone angle math | pending |
| 3l | Orchestrator end-to-end (Node 7) | pending |
| 3m | Camera move detection | pending |
| 3n | Production batch runner | pending |
| 3o | First real-rig validation (Jethalal) | pending |
| 3p | Documentation pass + first real episode test | pending |

See `docs/PHASE_3_ROADMAP.md` for what each phase ships.

## Locked decisions (do not re-litigate)

Resolved 2026-05-14 at project genesis. These are the architectural
commitments that downstream phases build on. If any of these need to
change later, it requires a NEW phase ship + canonical-file
reconciliation, not a silent override.

### 1. Adobe Animate CC as the assembly tool

Adobe Animate CC running on Windows is the canvas for clean animation
output. We do not switch tools (no Moho, no Blender, no Toon Boom)
because:

- Indian animation talent pool is largest for Animate
- Adobe CC infrastructure is already familiar to studios
- JSFL gives full programmatic control
- Auto Lip Sync is built in since CC 2018
- File format `.fla` is industry standard

**Pinned version: Adobe Animate CC 2020 (v20.x)** — installed on the
operator's Windows machine at `C:\Program Files\Adobe\Adobe Animate
2020\Animate.exe`. Newer versions (2022+) add Asset Warp tool for mesh
deformation, which we do NOT depend on in v1 — dynamic poses are
handled via symbol-swap on bone rotation (see decision #6).

### 2. Custom Python MCP server bridges Claude ↔ Animate CC

`animate_cc_pipeline/mcp_server/` is a Python MCP server that exposes
Animate-CC operations as tools Claude can call. Each tool generates a
parameterized JSFL script, writes it to a temp file, and invokes
`Animate.exe -AlwaysRunJSFL <script.jsfl>` to execute. Output (e.g.,
rendered MP4) is read back from disk.

**Why not direct file manipulation of `.fla`?** `.fla` is a binary
container (ZIP of XML, but Adobe-specific schema, undocumented in
places). JSFL is the supported, stable, programmatic interface.

### 3. Rigs must follow `RIG_SPEC_v1` contract

Every character rig used in this pipeline must conform to
`docs/RIG_SPEC_v1.md`. The spec covers:

- Layer naming (head, neck, torso, arm_L_upper, arm_L_lower, …)
- Bone naming + hierarchy (mirrors layer structure)
- Switch states for mouth shapes (Hindi phoneme set)
- Switch states for facial expressions
- Pivot conventions (rig center-of-mass at origin, character standing
  on Y=0)
- Default-pose metadata (default_height_units,
  default_shoulder_width_units, head_pivot_offset, feet_pivot_offset)

A rig validator (`rig_contracts/rig_validator.py`, Phase 3f) rejects
non-conforming rigs before processing. **No exceptions** — a rig that
doesn't validate cannot enter production.

### 4. Per-frame pose estimation (not per-keypose)

We run pose detection on **every frame** of the rough animatic, not
just the keyposes extracted by translation-aware diff. Reasons:

- Dynamic poses between keyposes need pose data to drive smooth bone
  motion through the tween
- Animate's tween-between-2-keyframes is unreliable for large bone
  rotations (rotates through body, doesn't bend elbow naturally)
- Per-frame keyframes + tiny tweens = motion exactly matches rough

Tool: **DWPose** (or anime-pose variant if accuracy on stylized
cartoons proves insufficient). Compute cost is acceptable — ~₹15-40K
per 22-min episode in cloud GPU.

### 5. The rough animatic IS the timing reference

No regenerating motion. No "AI fills in better timing." The client's
rough animatic has the timing they want; our job is to clean up the
drawings while preserving every frame's timing exactly.

Held frames (translation slides) are replayed via Animate's keyframe
+ classic tween. Pose changes become per-frame keyframes.

### 6. Dynamic poses: symbol-swap on bone rotation (no Asset Warp in v1)

Animate 2020 lacks Asset Warp (added in 2022). To handle dynamic poses
where the rig's default drawing would look wrong (extreme bend,
foreshortening, arm-overhead):

The rig contains **rotation-aware Graphic Symbols** for limbs that need
it — e.g., `arm_L_rotation_strip` is a Graphic Symbol with 8-12 frames,
each frame showing the arm at a different rotation (0°, 30°, 60°, 90°,
120°, 150°, 180°, etc.). JSFL drives the symbol's first-frame property
based on the parent bone's rotation:

```javascript
var frame_index = Math.round(bone_angle_degrees / 30) + 1;
arm_instance.firstFrame = frame_index;
arm_instance.loop = "single frame";
```

For TMKOC-style sitcom (snappy puppet feel is appropriate to genre),
discrete swap is fine. Smoother mesh-deformation interpolation is a v2
upgrade gated on Animate version + project budget.

### 7. Character placement: head-anchored, shoulder-width-scaled

For each character per frame:

- **Position**: place rig such that rig's head pivot matches pose's
  head joint (canvas coords). Head-based anchoring stays correct
  through pose changes (sitting/standing don't shift the head much).
- **Scale**: `scale = rough_shoulder_width / rig_default_shoulder_width`.
  Shoulder width is more pose-invariant than bbox height (which
  shrinks when character sits).
- **Z-order**: layer order by `bbox.bottom_y` — character with feet
  lower on canvas is in front.

### 8. Character identification: 3-layer fallback

1. **Layer 1 — Metadata**: `metadata.json` (operator-supplied) declares
   which characters are in each shot at which position (L/CL/C/CR/R).
2. **Layer 2 — Positional assignment (Strategy A)**: at the first
   keypose, sort detected blobs left→right and zip with metadata's
   position-sorted characters.
3. **Layer 3 — Temporal tracking**: for frames 2..N, assign each blob
   to its nearest neighbor in the previous frame (Hungarian assignment
   on Euclidean distance).
4. **Layer 4 — Manual override flag**: per-shot `identity_override.json`
   for the rare problem shot where 1–3 all fail. Operator names the
   blob explicitly.

### 9. Multi-character handling: per-character scale, no shared scale

Each character is scaled independently to its own bbox. Different
characters in the same frame can be at different scales — this
preserves the rough animatic's perspective by construction (artist
drew the background character smaller; the bbox is smaller; the
scaled rig is smaller).

### 10. Depth handling: bbox-driven, single rig per character in v1

The bbox's apparent size already encodes the rough's intended depth.
Per-character bbox → per-character scale = perspective preserved.

Detail/line-thickness mismatch at extreme distances accepted in v1
(daily-strip sitcom tolerates this; viewers don't notice).

**Deferred to v2:**

- Per-character distance variants (FG/MID/BG rigs)
- Background depth-zone annotations for sanity-checking
- Auto line-thickness compensation based on scale

### 11. Backward compatibility: schema-versioned manifests

All JSON manifests carry `schemaVersion: 1`. Additive changes are
allowed without bumping; field renames / removals / type changes
require schemaVersion bump + migration script + multi-release
deprecation window. Same discipline as the prior project.

### 12. Edge cases handled by animator review (15-20% of frames)

Auto-pipeline outputs a draft `.fla` + draft `.mp4` per shot. The
animator reviews and:

- Fixes ~10-15% of frames (bad pose estimation, occlusion, tracking
  drift)
- Manually draws ~5% (extreme poses no rotation strip covers)
- Adjusts comedy timing (frame-level micro-tuning)
- Validates expression keyframes (subtle facial work)

This is explicit scope: Claude does the mechanical 80-85%, the
animator does the creative 15-20%.

### 13. RunPod for pose estimation only, NOT for Animate

Animate CC has no Linux build and no headless mode. **All Animate
operations run on the operator's local Windows machine.** RunPod is
used only for:

- Per-frame pose estimation (DWPose / similar) — GPU-bound, cheap on
  RunPod
- Optional: background plate generation via image gen models

The orchestrator on the Windows machine offloads pose estimation to a
cloud GPU (RunPod) via simple HTTP API, then drives Animate locally
with the returned pose JSON.

## Environment gotchas

Captured here so a fresh Claude on a new device doesn't trip over
them:

- **No system Python on the operator's Windows machine.** Embedded
  Python is at `C:\Users\Omkar Hajare\Desktop\download\ComfyUI_windows_portable\python_embeded\python.exe`.
  All `run_*.py` wrappers must work under embedded Python (i.e., do
  the `sys.path` fixup pattern from the prior project's `run_node2.py`).
- **Claude Code's MCP server launcher needs a Python path it can
  find.** Since `python` isn't on PATH, the committed `.claude/settings.json`
  uses generic `"command": "python"` for portability across machines,
  but on this machine you must run
  `python tools/phase3/setup_local_python.py` once to generate
  `.claude/settings.local.json` (gitignored) with the embedded
  Python's absolute path. The setup script auto-detects ComfyUI's
  embedded Python if it's a sibling directory; pass `--python <path>`
  to override. Re-run after moving the ComfyUI install or switching
  machines.
- **Shell: Git Bash primary; PowerShell available.** Forward-slash
  paths work in Git Bash + Python; backslash paths required for some
  Windows commands.
- **Adobe Animate 2020 install path**:
  `C:\Program Files\Adobe\Adobe Animate 2020\Animate.exe`.
  Configured via `ANIMATE_CC_EXE` env var (in `.claude/settings.json`);
  override if installing elsewhere.
- **JSFL command-line invocation**:
  `Animate.exe -AlwaysRunJSFL <path/to/script.jsfl>` runs the script.
  BUT `fl.quit()` does NOT reliably exit Animate (Welcome screen,
  "save changes?" dialog, sign-in modal all block it silently). The
  JSFL bridge handles this by writing a sentinel file from JSFL,
  polling for it from Python, then force-killing Animate.exe via
  `taskkill /F /T /IM Animate.exe`. See `mcp_server/jsfl_bridge.py`
  + `mcp_server/README.md` "Animate.exe lifecycle" section.
- **`fl.saveDocument` vs `fl.saveDocumentAs` in JSFL.** The former
  saves to a URI you pass in; the latter IGNORES the URI parameter
  and opens the Save-As dialog, hanging JSFL. Always use
  `fl.saveDocument(doc, URI)` for headless saves. Discovered in
  Phase 3b-fixup-1.
- **Layer ops live on Timeline, not Document.** `doc.addNewLayer`
  does NOT exist in Animate 2020. Use
  `doc.getTimeline().addNewLayer(name, layerType)` instead. Same
  for `insertBlankKeyframe`, `currentFrame`. Discovered in Phase 3c.
- **Transform-order matters for `element.x` / `element.y`.** Apply
  transforms in this order: **rotation → scale → position**.
  Position LAST. JSFL's `element.x` / `element.y` represent the
  post-transform bounding-box top-left, which shifts under earlier
  rotation/scale. Setting position last gives a clean round-trip
  through save/reopen with ~1-2px float-drift. The orchestrator
  (Phase 3l) must follow this ordering when keyframing transforms
  per frame. Discovered in Phase 3d.
- **Keyframe insertion uses `convertToKeyframes`, not
  `insertKeyframe`.** `Timeline.insertKeyframe(N)` silently no-ops
  in some configurations even when the layer is selected. The
  reliable pattern is:
  1. `timeline.currentLayer = idx; timeline.setSelectedLayers(idx);`
  2. If frame past layer length: `timeline.insertFrames(N, false)`
     to extend
  3. `timeline.convertToKeyframes(frameIdx0, frameIdx0 + 1)`
  Use `convertToBlankKeyframes` for the blank variant. Discovered
  in Phase 3e.
- **`Timeline.clearKeyframes` hangs in Animate 2020.** Both the
  range and selection-based forms time out behind what appears to
  be an undismissable confirmation dialog. The `remove_keyframe`
  MCP tool is shipped for forward compat (likely works in
  Animate 2022+) but its smoke is skipped in v1. The orchestrator
  is insert-heavy, so this is acceptable. Discovered in Phase 3e.
- **`Timeline.convertToFrames` does NOT exist in Animate 2020.**
  Tested as a workaround for `clearKeyframes` in a Phase 3e-fixup
  attempt (2026-05-16). Animate threw `TypeError:
  timeline.convertToFrames is not a function` on line 34 of the
  rendered JSFL. The inverse operation is missing from Animate 2020's
  Timeline API even though `convertToKeyframes` /
  `convertToBlankKeyframes` exist. Adobe added `convertToFrames` in
  a later version. Workaround attempt reverted; do NOT re-test this
  on Animate 2020 — the answer is no.
- **Single-instance Animate behavior.** If Animate.exe is already
  running, a new `Animate.exe -AlwaysRunJSFL <script>` invocation
  delegates to the existing instance. The bridge auto-kills any
  running Animate before launch via `kill_existing_first=True`.
- **Adobe CC is subscription, version-pinned.** If the operator
  upgrades to Animate 2024/2025, JSFL behavior should be backward-
  compatible; we'll add a compatibility test in Phase 3o.
- **GitHub user: Omkar8369.** Repo will be public once first pushed.
- **RunPod EU-RO region** has the operator's persistent network
  volume (storyboard-models, 150 GB) from the prior project — same
  pod can host the pose-estimation worker.

## How to pick up where we left off (entrypoint for fresh Claude)

If you're a fresh Claude Code session that just opened this repo on
any device:

1. **Read this file** (CLAUDE.md). You're doing that.
2. **Read `docs/PLAN.md`** for the architecture.
3. **Read `docs/PHASE_3_ROADMAP.md`** for the phase plan + current
   position.
4. **Run `git log --oneline -20`** to see what was shipped recently.
5. **Check the Status table** above — find the topmost row marked
   "in progress" or "pending". That's where we resume.
6. **Run `python tools/phase3/validate_phase3_env.py`** (once it
   exists, after Phase 3a) to confirm the local environment is set
   up.
7. **For each pending phase**: discuss with the operator → lock
   decisions → update canonical files → write code → test → commit
   → push → "Run git pull".

If something seems contradictory between this file and code: this
file wins. Update the code or open a discussion with the operator.

## References

- Prior project (precursor): `animatic-refinement` repo at
  `C:\Users\Omkar Hajare\Desktop\download\animatic-refinement\` —
  see its `CLAUDE.md` for Nodes 1-11 architecture that informs ours
- Adobe Animate JSFL reference:
  https://help.adobe.com/en_US/as3/iprg/WS5b3ccc516d4fbf351e63e3d118a9b89b65-7fe4.html
- MCP protocol spec: https://modelcontextprotocol.io/
