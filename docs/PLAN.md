# Animate CC Pipeline — Architecture Plan

## Context

This pipeline produces production-grade Indian 2D-cartoon animation
(TMKOC-style, daily-strip viable) by orchestrating **Adobe Animate CC**
via **Claude Code + a custom MCP server**.

**Problem being solved:** Traditional 2D animation studios charge
₹40-70 lakh per 22-min episode and require 40-50 artists working
4-6 weeks. AI image generation (Flux, SDXL with LoRAs) achieves only
~70-80% character identity consistency — not good enough for
production. AI video generation (Veo/Kling) is inconsistent and
expensive per second.

**This pipeline's bet:** Pre-built rigged characters + Claude
orchestrating Animate CC = production-grade output at ~5-10% the
cost of traditional 2D, with 8-12 person teams instead of 40-50.

**Inputs:**

- Rough animatic MP4 (per shot, post-shot-split)
- `metadata.json` (operator-supplied; characters, positions, durations)
- `characters.json` (operator-supplied; character library + sheet
  references — same shape as the prior `animatic-refinement` project)
- Rigged character `.fla` files conforming to `RIG_SPEC_v1`
- Hindi audio WAV per shot (optional; for lipsync)
- Background plate PNG per location

**Outputs:**

- Auto-animated `.fla` per shot (animator opens, reviews, tweaks)
- Draft MP4 per shot (for QC review)
- Final MP4 per shot (after animator + editor pass)

**Target platform:**

- **Local Windows machine** runs Adobe Animate CC (mandatory — no
  headless Animate)
- **RunPod EU-RO** for GPU-bound work (pose estimation, optional
  background generation)
- **Claude Code** orchestrates both via local MCP server + remote
  HTTP

## NODE-WISE STRUCTURAL PLAN

### Node 1 — Project Input & Setup Interface

**(Reused from `animatic-refinement` repo, ported here verbatim in
Phase 3a's followup.)**

Two static HTML pages with `localStorage` persistence:

- `characters.html` — Character Library page. Operator pre-registers
  each character with model sheet PNG, identity name, and rig
  filename. Saves `characters.json` and `<name>_sheet.png`.
- `index.html` — Shot Metadata Form. Operator fills in per-shot:
  `shot_id`, `mp4_filename`, character list (identity + position
  L/CL/C/CR/R), duration in frames. Saves `metadata.json`.

No server. Browser-only. Files delivered via `Blob` download.

Schema unchanged from prior project except:

- `CharacterSpec` gains `rigFilename: str` (relative to `rigs/`),
  `defaultHeightUnits: int`, `defaultShoulderWidthUnits: int` — Phase
  3a adds these schema fields (additive; old `characters.json` still
  load via defaults).

### Node 2 — Metadata Ingestion & Validation

Pure-Python, no GPU. Pydantic v2 schema validation. Hard-fails on
any error; lists all offenders for one-pass operator fix.

Loads `metadata.json` + `characters.json`. Cross-references every
MP4 filename, sheet filename, rig filename exists on disk. Builds
`queue.json` (`schemaVersion: 1`, ordered shot list, absolute paths,
chunked by `batchSize`).

**Diverges from prior project:** Each character's `rigFilename` must
resolve to an existing `.fla` in `rigs/`, validated against
`RIG_SPEC_v1` via `rig_validator.py` (Phase 3f). Rigs failing
validation cause Node 2 to fail the whole batch — no exceptions.

### Node 3 — Shot Pre-processing (MP4 → PNG Sequence)

Pure-Python. Uses `imageio-ffmpeg` pip wheel (static ffmpeg binary,
no system dep). Per-shot PNG sequences at 25 FPS, 1-indexed,
4-digit padding (`frame_NNNN.png`).

Identical to prior project's Node 3. Rerun wipes stale frames.

### Node 4 — Key Pose Extraction

Pure-Python (numpy FFT + scipy). Phase correlation recovers
per-frame translation `(dy, dx)`; aligned MAE on downscaled
grayscale (max_edge=128) scores similarity post-translation.

Frames with aligned MAE > threshold (default 8.0) start a new key
pose; held frames stored with `(dy, dx)` offset for Node 9 replay.

Identical to prior project's Node 4.

### Node 5 — Character Detection & Position

Pure-Python (scipy.ndimage). Otsu binarization (or luminance
pre-threshold from Phase 2f of prior project) → connected components
→ bbox per character → positional identity assignment (Strategy A:
left-to-right by center-x, zipped with metadata's position-sorted
characters).

Per-character bbox stored at original frame resolution. Includes
center_x, center_y, w, h, bottom_y for downstream placement +
z-order.

Reconcile pass (`binary_erosion` up to 3 iterations) when blob count
doesn't match metadata. Warnings, not errors.

### Node 6 (NEW) — Per-Frame Pose Estimation

GPU-bound. **Runs on RunPod**, not locally.

For each frame of each shot, for each character bbox:

- Crop frame to bbox (with 20% margin)
- Run DWPose model → joint coordinates
- Output: 17 joints per character per frame
  (nose, eyes, ears, shoulders, elbows, wrists, hips, knees, ankles)

Writes `pose_map.json` per shot:

```json
{
  "schemaVersion": 1,
  "shotId": "shot_001",
  "frames": {
    "1": {
      "TAPPU": { "head": [320, 180], "neck": [320, 220], ... },
      "JETHALAL": { ... }
    },
    "2": { ... }
  }
}
```

If DWPose confidence per joint is below threshold (e.g., 0.4), the
joint is marked `null` and Node 7's bone math falls back to interpolation from previous reliable frame.

Aggregate `node6_result.json` with one summary per shot.

### Node 7 (NEW) — Animate CC Orchestrator

The main course. Runs **locally on Windows** (where Animate is
installed). For each shot in the queue:

1. **Read inputs**: `queue.json`, `node5_result.json`,
   `pose_map.json`, audio WAV if present, background PNG.

2. **Build the Animate document** via MCP:
   - `open_new_document(width=1920, height=1080, fps=25)`
   - `import_animatic_reference(rough_mp4, layer="REF_ANIMATIC")`
   - `import_background_image(bg_png, layer="BG", frame=1)`

3. **For each character in the shot:**
   - `import_character_rig(rigs/<identity>.fla)`
   - `add_layer(name=identity)`
   - For each frame 1..N:
     - Compute canvas position from bbox (head-anchored, see
       decision #7)
     - Compute scale from shoulder width
     - Compute bone angles from pose joints (see
       `pose_to_bones.py`)
     - For limbs with rotation strips (Smart-Bone-equivalent): set
       Graphic Symbol firstFrame based on bone angle (see decision #6)
     - `insert_keyframe(layer=identity, frame=N)` with all the above

4. **Audio + lipsync:**
   - `import_audio(audio_wav, layer="AUDIO", frame=1)`
   - `apply_auto_lipsync("AUDIO", "<identity>_MOUTH")` per character

5. **Camera moves** (Phase 3m):
   - Detected from rough by frame-correlation pan/zoom detection
   - `set_camera_position(frame, x, y, zoom, rotation)`

6. **Save + render:**
   - `save_document(out_dir/<shot_id>/auto_animated.fla)`
   - `render_to_mp4(out_dir/<shot_id>/draft.mp4, fps=25, range=(1, N))`

Animator opens `auto_animated.fla` for review and touch-ups.

### Node 8 onward — replaced by Animate

Prior project's Nodes 8 (compositing), 9 (timing reconstruction),
and 10 (PNG→MP4) are obsoleted here — Animate handles compositing,
timeline, and MP4 export natively.

### Node 11 — Batch Management

Production-grade per-shot driver. **Shipped in Phase 3n** as
`pipeline/batch_runner.py` (`run_batch`) + `pipeline/cli_batch.py`
+ repo-root `run_batch.py`. Reads a `batch_config.json` describing
N shots; runs `shot_processor.process_shot` per shot with a
configurable retry policy (default: 2 retries = up to 3 attempts
per shot). Emits two artifacts:

- `batch_progress.jsonl` — one JSON line per attempt, status one of
  `succeeded / retrying / exhausted`. Append-only so a partial run
  is parseable up to the last completed event.
- `batch_report.json` — aggregate `BatchReport` (started/finished
  timestamps, total attempts, list of final per-shot `ShotAssembly`).

CLI exit codes: 0 all-OK, 1 some shot failed after retries, 2 setup
error (bad config, can't write report, etc.).

**Diverges from prior project:**

- Node 6 (pose estimation) is HTTP-call to RunPod worker, not local
  subprocess
- Node 7 (Animate orchestrator) requires Animate.exe on PATH or via
  `ANIMATE_CC_EXE` env var
- Pre-Node-7 check: validate every `rigFilename` in `queue.json`
  passes `rig_validator.py`
- In-line pose detection + camera-move detection are NOT auto-chained;
  operators run `cli_node6_pose` and `cli_camera_detector` as
  preprocessing and reference the resulting JSON via `pose_map_path`
  / `camera_moves_path` in the batch config.

## The MCP server

`animate_cc_pipeline/mcp_server/` is a Python MCP server that
Claude Code talks to over the MCP protocol. It exposes Animate
operations as tools:

### Document tools (Phase 3c)

- `open_new_document(width, height, fps)` → document handle
- `save_document(path)`
- `close_document()`
- `import_animatic_reference(mp4_path, layer_name)`
- `import_background_image(png_path, layer_name, frame)`
- `import_character_rig(fla_path)`

### Symbol placement (Phase 3d)

- `place_symbol_instance(symbol, layer, x, y, frame)` → instance id
- `set_instance_position(instance_id, frame, x, y)`
- `set_instance_scale(instance_id, frame, sx, sy)`
- `set_instance_rotation(instance_id, frame, angle)`

### Keyframing (Phase 3e)

- `insert_keyframe(layer, frame)`
- `insert_blank_keyframe(layer, frame)`
- `remove_keyframe(layer, frame)`
- `get_keyframes(layer)` → list of frame numbers

### Bones (Phase 3f)

- `list_bones(rig_instance_id)` → list of bone paths
- `set_bone_angle(rig_instance, bone_path, frame, angle_degrees)`
- `set_bone_position(rig_instance, bone_path, frame, x, y)`
- `set_graphic_first_frame(instance_id, frame_index)`
  *(for rotation-strip symbol swapping)*

### Tweens (Phase 3g)

- `add_motion_tween(layer, start_frame, end_frame)`
- `add_classic_tween(layer, start_frame, end_frame)`
- `set_easing(layer, frame_range, easing_curve)`

### Audio + lipsync (Phase 3h)

- `import_audio(audio_path, layer, frame)`
- `apply_auto_lipsync(audio_layer, mouth_switch_symbol)`
- `set_switch_state(layer, frame, state_name)`

### Camera (Phase 3i)

- `set_camera_position(frame, x, y, zoom, rotation)`

### Render (Phase 3i)

- `render_to_mp4(out_path, fps, range)`
- `render_preview(start_frame, end_frame)`

### Utilities

- `get_stage_info()` → { width, height, fps, totalFrames, layers }
- `list_library_symbols()`
- `list_layers()`
- `validate_rig_against_spec(rig_instance, contract_path)`

## How JSFL is invoked

Under the hood, every MCP tool:

1. Composes a parameterized JSFL script from a template in
   `mcp_server/jsfl_templates/`
2. Writes it to a temp file
3. Invokes `Animate.exe -AlwaysRunJSFL <script.jsfl>` via subprocess
4. Reads result from a designated output file (JSON or PNG/MP4)
5. Returns to Claude

Animate.exe needs to be running for some operations (document
manipulation) and can run headlessly for others (export). Phase 3b
nails down the boot strategy.

## Critical files / artifacts produced

- `<work_dir>/<shot_id>/auto_animated.fla` — auto-generated Animate
  file with rig placed, keyframed, tweened, lipsynced
- `<work_dir>/<shot_id>/draft.mp4` — draft render for animator
- `<work_dir>/<shot_id>/pose_map.json` — Node 6 output
- `<work_dir>/<shot_id>/animate_assembly.json` — Node 7 output
  manifest (per-frame what was placed, seeds, decisions)
- `<work_dir>/<shot_id>/final.mp4` — after animator review + editor

## Reusable / external components

- **Adobe Animate CC 2020** — local Windows install (assembly tool)
- **DWPose** — pose estimation model (RunPod)
- **imageio-ffmpeg** — Node 3 video decode (pip wheel)
- **scipy.ndimage** — Node 4 + 5 (numpy/scipy)
- **pydantic v2** — schema validation
- **mcp** — Anthropic MCP protocol library

## Verification (end-to-end test)

Phase 3p deliverable: take a real TMKOC-style rough animatic shot
through the full pipeline and produce an animated MP4 that:

1. Has the right characters at the right positions in every frame
2. Matches the rough's timing exactly
3. Has working Hindi lipsync
4. Has correct z-order in multi-character shots
5. Renders in under 5 minutes per 5-second shot on the local Windows
   machine
6. Requires < 30 minutes of animator touch-up for the test shot

## Follow-up (not in this plan, deferred to v2)

- Per-character distance variants (FG/MID/BG rigs) for premium
  detail consistency
- Asset Warp / mesh deformation (requires Animate 2022+)
- Background depth-zone annotations for auto-scale correction
- Real-time preview during Claude orchestration (we currently
  batch-process then animator opens result)
- Multi-shot batch parallelism (Phase 3n shipped sequential per-shot
  processing; concurrent shot processing is deferred — the embedded
  Animate process serializes JSFL anyway, so a fan-out would gate on
  multiple Animate launches, not free)
- Automatic shot splitter from full-episode animatic (Phase 3n only
  scopes per-shot input; full-episode auto-split is v2)
