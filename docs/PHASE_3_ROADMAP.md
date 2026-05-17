# Phase 3 Roadmap

Phase-by-phase ship plan for the Animate CC Pipeline. Each row =
one commit, one ship-checklist pass, one canonical-file
reconciliation, drift-grep clean.

**This file is canonical (one of the six). Update it whenever a phase
ships.**

## Discipline

- One phase per commit
- Each phase has: locked decisions added to `CLAUDE.md` (if any), code
  + tests, canonical-file sync, drift-grep, push, "Run `git pull`"
  notice to operator
- Never skip ahead — Phase 3b cannot start until 3a is shipped
- Bug-fix phases inserted as `3<letter>-fixup-N` when post-ship debug
  catches something (same convention as prior project)

## Phase status legend

- **In progress** = current commit in flight
- **Shipped (date)** = on `origin/main`, "Run git pull" announced
- **Pending** = not started

## The phases

### Phase 3a — Project scaffold + canonical files + 13 locked decisions

**Status:** Shipped 2026-05-14 (commit `0440c04`).

**Ships:**

- New repo `animate-cc-pipeline/` with full directory tree
- `CLAUDE.md` with 13 locked architectural decisions, status table,
  pickup instructions
- `README.md` human-facing entrypoint
- `docs/PLAN.md` full architecture description
- `docs/PHASE_3_ROADMAP.md` (this file)
- `docs/RIG_SPEC_v1.md` rig contract
- Subsystem READMEs (`animate_cc_pipeline/`, `mcp_server/`, `rigs/`)
- `requirements.txt` with mcp / pydantic / opencv-python pins
- `.gitignore` for Python, Animate temp files, worktrees
- `.claude/settings.json` registering animate-cc MCP server
- Initial commit + push to `origin/main`

**No code yet.** Phase 3a verifies the discipline + canonical sync
before any implementation. The 16 phases that follow each ship
incremental capability.

**Drift-grep targets:** no phase later than 3a marked as "DONE"
anywhere; all six canonical files reference each other consistently.

---

### Phase 3b-fixup-1 — Real-world Animate-launch fixes (2026-05-15)

**Status:** In progress (this commit)

**What turned up during Phase 3b validation:**

1. **`fl.saveDocumentAs(doc, URI)` is broken in Animate 2020** — it
   silently ignores the URI parameter and opens the interactive
   Save-As dialog, hanging JSFL. The right call is
   `fl.saveDocument(doc, URI)`. `hello_world.jsfl` updated.
2. **`fl.quit()` doesn't actually exit Animate.** Welcome screens,
   "save changes?" dialogs, and Creative Cloud sign-in prompts
   silently block the quit. Animate.exe stays resident at ~500 MB.
3. **Single-instance behavior.** When Animate is already running,
   `Animate.exe -AlwaysRunJSFL <script>` delegates to the existing
   instance and the new process exits immediately — the JSFL may
   or may not run depending on the existing instance's state.
4. **Smoke ran as a script fails on sys.path.** Running the smoke
   via `python animate_cc_pipeline/tests/_smoke_phase3b.py` doesn't
   add the repo root to sys.path; the `from animate_cc_pipeline...`
   imports fail. Pytest adds it automatically but standalone scripts
   need the same `sys.path.insert(0, repo_root)` pattern the prior
   project's run_node*.py wrappers use.
5. **`requirements.txt` upper bounds too tight.** numpy<2, Pillow<12,
   pytest<9 forced pip to downgrade ComfyUI's already-newer installs
   and rebuild from source on Python 3.13. The build backend
   (`mesonpy`) isn't preinstalled. Upper bounds removed.

**Architectural fix: sentinel-polling + force-kill pattern.**

The bridge no longer waits for Animate to exit. Instead:
- Force-kills any running `Animate.exe` before launch
  (`kill_existing_first=True`)
- Launches via `subprocess.Popen` (non-blocking)
- Polls filesystem for `expected_outputs` (the real .fla + a
  sentinel the JSFL writes)
- Force-kills `Animate.exe` once outputs land

This treats Animate as a deterministic black-box renderer. Smoke
end-to-end now takes ~15-25s (cold boot Animate, run JSFL, save .fla,
write sentinel, kill Animate).

**Ships:**

- `mcp_server/jsfl_bridge.py` — full rewrite around the
  `expected_outputs` + polling design. `JsflResult` gains
  `completed_normally`, `elapsed_seconds`, `missing_outputs` fields.
  New helpers: `_kill_animate`, `_animate_running`. Backward-compat
  fallback (no `expected_outputs` → subprocess.run wait-for-exit).
- `mcp_server/jsfl_templates/hello_world.jsfl` — uses
  `fl.saveDocument` (not `fl.saveDocumentAs`), writes a sentinel
  file before `fl.quit()` (the quit is best-effort; Python kills
  Animate regardless).
- `tests/test_jsfl_bridge.py` — rewritten to match new bridge API.
  17 unit tests pass; 1 integration test (gated by
  `SKIP_ANIMATE_TESTS=1` env var or missing Animate.exe).
- `tests/_smoke_phase3b.py` — sys.path fixup at top so it runs as
  a standalone script. Uses new `expected_outputs` API with
  sentinel.
- `requirements.txt` — all upper bounds removed. Lower bounds only.
- `mcp_server/README.md` — extended "Animate.exe lifecycle" section
  with the actual gotchas discovered during the spike.

### Phase 3b — MCP server scaffold + hello-world JSFL

**Status:** Shipped 2026-05-14 (commit `33aeb49`); functional after
Phase 3b-fixup-1 (this commit, 2026-05-15).

**Ships:**

- `animate_cc_pipeline/__init__.py` + `mcp_server/__init__.py` +
  `tests/__init__.py` package inits
- `mcp_server/server.py` MCP protocol handler exposing the `ping`
  tool (returns `{ status, server_name, server_version, animate_cc_exe }`)
- `mcp_server/jsfl_bridge.py` parameterized JSFL template runner;
  resolves Animate.exe via `ANIMATE_CC_EXE` env var or default path;
  escapes Windows backslashes for JSFL string literals
- `mcp_server/jsfl_templates/hello_world.jsfl` creates a 1920×1080
  25 FPS empty document and saves it via `FLfile.platformPathToURI`
- `tests/test_mcp_server_boots.py` — unit tests (imports, list_tools,
  call_tool, unknown-tool-error). No Animate.exe needed.
- `tests/test_jsfl_bridge.py` — unit tests for template rendering +
  optional integration test (gated by SKIP_ANIMATE_TESTS env var)
- `tests/_smoke_phase3b.py` — end-to-end smoke script (manual run)
- `tools/phase3/setup_local_python.py` — auto-detects ComfyUI
  embedded Python (or system Python or env var) and writes
  `.claude/settings.local.json` (gitignored) so Claude Code can
  launch the MCP server on this machine

**Documentation updates:**

- CLAUDE.md status table: 3a → Shipped, 3b → In Progress
- CLAUDE.md environment gotcha: new entry on Python-finding via
  `setup_local_python.py`
- `mcp_server/README.md` extended with Animate.exe lifecycle notes
  (boot time, JSFL invocation, exit code semantics, the URI gotcha)

**Phase 3b "done" criteria:** unit tests pass via
`<embedded python> -m pytest animate_cc_pipeline/tests/test_mcp_server_boots.py
animate_cc_pipeline/tests/test_jsfl_bridge.py -v`. Smoke test
`_smoke_phase3b.py` creates a `.fla` on disk via Animate.exe when
run manually. Claude Code can call `ping` and receive a JSON response.

---

### Phase 3c — Document tools

**Status:** Shipped 2026-05-16 (commit `680b6f3`). 34 unit tests pass;
end-to-end smoke creates a `.fla` with an embedded image layer
(.fla grew 3801 → 4615 bytes) in ~46 seconds across 3 Animate
launches. Discovered + documented Animate gotcha: `doc.addNewLayer`
does not exist; layer ops are on `doc.getTimeline()`.

**Ships (revised scope from original 3c plan):**

- `mcp_server/tools/__init__.py` — package init for tool categories
- `mcp_server/tools/document.py` with **5 MCP tools**:
  - `create_document(fla_path, width, height, fps)` — creates a
    new `.fla` at the given path with the given canvas dimensions
    and frame rate
  - `save_document(fla_path)` — opens an existing `.fla`, saves it,
    closes it. Useful as an integrity check + as a no-op between
    other tools
  - `close_document()` — utility that force-kills any running
    `Animate.exe` (cleanup after a hung tool call). Stateless.
  - `import_image_as_layer(fla_path, image_path, layer_name, frame)`
    — opens `.fla`, adds a new layer named `layer_name`, imports
    PNG/JPG at the given frame, saves and closes. Covers
    "background plate" use case.
  - `import_video_as_layer(fla_path, mp4_path, layer_name, frame)`
    — same shape but imports MP4 as embedded video. Covers
    "animatic reference layer" use case for Phase 3l orchestration.
- JSFL templates in `mcp_server/jsfl_templates/`:
  - `create_doc.jsfl`
  - `save_doc.jsfl`
  - `import_image.jsfl`
  - `import_video.jsfl`
- `server.py` updated to register the 5 new tools alongside `ping`
- `tests/test_document_tools.py` — unit tests (no Animate spawn)
  covering tool registration, parameter validation, JSFL template
  substitution
- `tests/_smoke_phase3c.py` — end-to-end smoke that:
  1. creates a new .fla
  2. imports a PIL-generated 16×16 PNG onto a "BG" layer
  3. re-opens the .fla via save_document (integrity check)
  4. verifies the .fla still exists and grew in size
- `mcp_server/README.md` extended with per-tool documentation

**Deferred from original 3c plan to a later phase:**

- `import_character_rig(fla_path)` — importing another `.fla` as
  External Library is its own JSFL operation; will ship in Phase 3d
  alongside symbol placement (which is the immediate consumer of
  library symbols).

**Phase 3c "done" criteria:** Unit tests pass via
`<python> -m pytest animate_cc_pipeline/tests/test_document_tools.py`.
Smoke test creates a `.fla` with an image layer and saves it
successfully. Each tool's per-call wall time is ~20-25s (one
Animate launch per call; long-running instance reuse deferred to
Phase 3i).

---

### Phase 3d — Symbol placement tools

**Status:** Shipped 2026-05-16 (commit `a2df524`). 49 unit tests
pass; smoke applies rotation 45°, scale 2.0, position (500, 300)
to an imported image — readback after save/reopen confirms all
three transforms survive within float-drift tolerance (~2px for
position, ~0.01 for scale, ~0.1° for rotation). Wall time ~90s
across 6 Animate launches. Gotcha #4 documented: apply transforms
in order rotation → scale → position (position LAST).

**Ships:**

- `tools/symbol.py` with **4 MCP tools**:
  - `place_symbol_instance(fla_path, symbol_name, layer_name, frame, x, y)`
    — places an instance of an existing library symbol onto a layer
    at given frame and stage coordinates. Auto-creates the layer if
    not present.
  - `set_instance_position(fla_path, layer_name, frame, x, y)` —
    moves the first element on layer+frame to (x, y).
  - `set_instance_scale(fla_path, layer_name, frame, sx, sy)` —
    sets scaleX/scaleY of the first element on layer+frame.
  - `set_instance_rotation(fla_path, layer_name, frame, angle)` —
    sets rotation (degrees) of the first element on layer+frame.

**Identification model**: tools identify the target instance by
**layer name + frame number** (assumes one element per layer per
frame, which matches the rigging workflow — one rig per layer per
shot). Layer-name resolution scans `doc.getTimeline().layers` for a
matching `.name`; frame number is 1-indexed externally and converted
to 0-indexed internally for JSFL.

**Deferred**:

- `import_character_rig(fla_path, rig_fla_path)` — importing
  another `.fla`'s library is its own JSFL pattern
  (`fl.openExternalLibrary` then copy). Will ship in 3d-fixup or
  alongside Phase 3o's first real-rig validation if the orchestrator
  needs it then.
- `list_library_symbols`, `list_layers`, `get_stage_info` —
  introspection utilities; Phase 3i grouping.

**JSFL templates** in `mcp_server/jsfl_templates/`:
- `place_symbol_instance.jsfl`
- `set_instance_position.jsfl`
- `set_instance_scale.jsfl`
- `set_instance_rotation.jsfl`

**Smoke test (`_smoke_phase3d.py`)**:
1. `create_document` (new .fla)
2. `import_image_as_layer` (puts a PNG on layer "BG" — gives us an
   element to manipulate)
3. `set_instance_position` to (500, 300)
4. `set_instance_scale` to (2.0, 2.0)
5. `set_instance_rotation` to 45°
6. Reopen .fla and verify the element's properties match

**Tests**: ~12-15 unit tests covering tool registration, JSFL
template presence + placeholder validation, argument validation,
error paths for missing layer/frame/file.

**Phase 3d "done" criteria**: unit tests pass via pytest; smoke
verifies set_instance_* applied changes survive a save/reopen
cycle. Wall time ~80-120s (4-5 Animate launches in sequence).

---

### Phase 3e — Keyframe tools

**Status:** In progress (2026-05-16)

**Ships:**

- `tools/keyframe.py` with **4 MCP tools**:
  - `insert_keyframe(fla_path, layer_name, frame)` — insert a keyframe
    at given frame (inherits content from preceding keyframe). The
    layer auto-extends if `frame` is past the layer's current end.
  - `insert_blank_keyframe(fla_path, layer_name, frame)` — same shape
    but starts the keyframe with no content (clean slate).
  - `remove_keyframe(fla_path, layer_name, frame)` — clears the
    keyframe status of `frame`, so that frame now extends from the
    preceding keyframe. Does NOT delete the frame slot.
  - `get_keyframes(fla_path, layer_name)` — READ-ONLY tool. Returns a
    JSON list of 1-indexed frame numbers on which `layer_name` has
    keyframes. Used by the orchestrator (and the smoke) to verify
    keyframe placement after write tools.

**Identification model**: layer name + 1-indexed frame number, same
as Phase 3d. JSFL is 0-indexed internally; conversion handled in
the templates.

**`get_keyframes` JSON readback pattern**: the JSFL writes its result
to a temp JSON file (path supplied as `{{OUT_JSON_PATH}}`); Python
reads it and folds the content into the TextContent response. Same
pattern as Phase 3d's verification helper.

**JSFL templates** in `mcp_server/jsfl_templates/`:
- `insert_keyframe.jsfl`
- `insert_blank_keyframe.jsfl`
- `remove_keyframe.jsfl`
- `get_keyframes.jsfl`

**Smoke test (`_smoke_phase3e.py`)**:
1. `create_document` + `import_image_as_layer` (layer "BG", frame 1)
2. `get_keyframes("BG")` → expect `[1]`
3. `insert_keyframe("BG", frame=10)` → adds keyframe at 10
4. `insert_blank_keyframe("BG", frame=20)` → adds blank at 20
5. `get_keyframes("BG")` → expect `[1, 10, 20]`
6. `remove_keyframe("BG", frame=10)` → clears keyframe at 10
7. `get_keyframes("BG")` → expect `[1, 20]`

**Tests**: ~14-18 unit tests covering registration, JSFL template
placeholders, argument validation, dispatcher routing,
`get_keyframes` JSON readback parsing.

**Phase 3e "done" criteria**: unit tests pass; smoke completes the
7-step round-trip with `get_keyframes` returning the expected lists.
Wall time ~120-150s (7 Animate launches).

**Phase 3e ship outcome (2026-05-16)**: 3 of 4 tools verified end-to-
end on Animate 2020. `remove_keyframe` shipped with a known
limitation — `Timeline.clearKeyframes` (both range and selection-
based forms) hangs JSFL behind an undismissable dialog on this
version. Tool description documents the limitation; smoke skips its
live verification. Likely works on Animate 2022+; will be re-tested
when the operator's environment upgrades. Two additional gotchas
documented: `insertKeyframe` silently no-ops (workaround:
`convertToKeyframes`), and `clearKeyframes` hangs. Defer
`remove_keyframe` re-enablement to a future fixup phase.

---

### Phase 3f — Bone tools + rig contract validator + template rig

**Status:** In progress (2026-05-16) — pragmatic scope revision.

**Scope revision rationale**: original plan listed `list_bones` /
`set_bone_angle` / `set_bone_position` as primary tools. Two
realities after Phase 3d-3e gotcha load:

1. Armature-bone manipulation requires a properly-rigged `.fla`
   with a bone armature already present (Animate's Bone tool is
   interactive; JSFL armature creation is rough).
2. RIG_SPEC_v1 decision #6 documents that Animate 2020 uses
   **rotation strips on Graphic Symbols** as the Smart-Bone
   substitute. The orchestrator's per-frame transform updates
   primarily drive `graphic.firstFrame` to switch limb drawings —
   NOT raw bone-angle manipulation.

So Phase 3f reframes around graphic-first-frame (the actual rigging
primitive we need) and defers armature-bone tools.

**Ships:**

- `tools/bone.py` with 3 MCP tools:
  - `set_graphic_first_frame(fla_path, layer_name, frame, target_first_frame, loop_mode)` —
    sets `firstFrame` and `loop` on a Graphic Symbol instance.
    Rotation-strip control: pose angle maps to a strip frame index.
  - `get_graphic_first_frame(fla_path, layer_name, frame)` — READ
    helper. Returns current firstFrame + loop mode.
  - `validate_rig(fla_path, identity)` — runs the rig validator,
    returns JSON report.
- `rig_contracts/rig_validator.py` — Python validation logic.
  Reads structure JSON from `dump_rig_structure.jsfl`, validates
  against RIG_SPEC_v1 rules.
- `rig_contracts/__init__.py` — package init.
- `mcp_server/jsfl_templates/dump_rig_structure.jsfl` — extracts
  rig structure as JSON (layers, switch states, library items,
  Graphic Symbol frame counts, metadata layer JSON).

**Deferred (honest scope reduction)**:

- `list_bones`, `set_bone_angle`, `set_bone_position`
- `rigs/_template/template_character.fla`

  *Reason*: all need a real armature-rigged `.fla` to test against;
  JSFL armature creation is rough. Will land in Phase 3f-fixup or
  alongside Phase 3o once a rigger provides a real test fixture.

**JSFL templates**:
- `set_graphic_first_frame.jsfl`
- `get_graphic_first_frame.jsfl`
- `dump_rig_structure.jsfl`

**Smoke (`_smoke_phase3f.py`)**:
1. `create_document`, then build a Graphic Symbol "RotationStrip"
   with 3 blank keyframes via JSFL (`library.addNewItem` +
   `editItem` + insertBlankKeyframe loop).
2. Place a RotationStrip instance on layer "ARM" frame 1.
3. `get_graphic_first_frame("ARM", 1)` → default firstFrame.
4. `set_graphic_first_frame("ARM", 1, target=2, loop="single frame")`.
5. `get_graphic_first_frame("ARM", 1)` → firstFrame=2,
   loop="single frame".
6. `validate_rig` on the test `.fla` → expect FAIL with structured
   missing-field errors. Validates the validator's negative path.

**Tests**: ~18-22 unit tests covering tool registration, JSFL
placeholders, argument validation, rig_validator rule methods on
synthetic JSON fixtures.

**Phase 3f done criteria**: unit tests pass; smoke round-trips
`set_graphic_first_frame`; validator correctly flags the bad smoke
rig. Wall time ~120-180s.

---

### Phase 3g — Tween tools

**Status:** In progress (2026-05-16)

**Ships:**

- `tools/tween.py` with **3 MCP tools**:
  - `add_classic_tween(fla_path, layer_name, start_frame)` — sets
    `frame.tweenType = "motion"` on the keyframe at start_frame.
    Animate then interpolates position/rotation/scale to the next
    keyframe on that layer. (This is Animate's "Classic Tween" —
    the older but cleanest JSFL API, what the orchestrator
    naturally uses.)
  - `add_motion_tween(fla_path, layer_name, start_frame, end_frame)`
    — invokes `Timeline.createMotionObject(start, end)` to create
    a modern Motion Tween span. Tagged experimental — Phase 3e's
    clearKeyframes hang showed that some newer JSFL APIs misbehave
    on Animate 2020.
  - `set_easing(fla_path, layer_name, frame, easing)` — sets
    `frame.tweenEasing` on the starting keyframe of a tween.
    Range -100 to +100: 0 = linear, -100 = ease-in only, +100 =
    ease-out only.

**JSFL templates** in `mcp_server/jsfl_templates/`:
- `add_classic_tween.jsfl`
- `add_motion_tween.jsfl`
- `set_easing.jsfl`

**Verify helper** `tests/_verify_phase3g.jsfl` reads `tweenType` +
`tweenEasing` for a frame and writes JSON the smoke asserts against.

**Smoke (`_smoke_phase3g.py`)**:
1. `create_document` + `import_image_as_layer` (layer "BG", frame 1
   has image instance).
2. `insert_keyframe` at frame 30 (need two keyframes to tween between).
3. `set_instance_position` at frame 30 to (500, 300) — actual motion
   to interpolate.
4. `add_classic_tween` at frame 1.
5. `set_easing` at frame 1 to +50 (ease-out).
6. Verify via `_verify_phase3g.jsfl`: frame 1's tweenType="motion",
   tweenEasing=50.
7. `add_motion_tween` over frames 1-30 (best-effort; if it errors
   on Animate 2020 we document like `remove_keyframe` was).

**Tests**: ~14-16 unit tests covering registration, JSFL placeholders,
argument validation, dispatcher routing, easing range validation.

**Phase 3g done criteria**: unit tests pass; classic tween + easing
verified round-trip; motion tween either verified or documented-as-
deferred with the same honest-shipping pattern Phase 3e + 3f used.

---

### Phase 3h — Audio + lipsync tools

**Status:** In progress (2026-05-16)

**Ships:**

- `tools/audio.py` with **3 MCP tools**:
  - `import_audio(fla_path, audio_path, layer_name, frame)` —
    imports a WAV/MP3 + places instance on a layer at frame.
  - `set_switch_state(fla_path, layer_name, frame, state_name)` —
    pins a Switch-style Graphic Symbol to its frame labeled
    `state_name`. Used for mouth shapes / facial expressions.
  - `apply_auto_lipsync(fla_path, audio_layer, mouth_layer)` —
    EXPERIMENTAL. JSFL surface limited.

**JSFL templates**: import_audio.jsfl, set_switch_state.jsfl,
apply_auto_lipsync.jsfl, _setup_phase3h_test_fla.jsfl (smoke helper
that builds a Graphic Symbol with frame labels).

**Smoke (`_smoke_phase3h.py`)**:
1. `create_document`
2. Generate a 0.5s silent WAV via Python `wave` stdlib.
3. `import_audio` onto layer "AUDIO" frame 1.
4. Build "MouthSwitch" with 3 named frames (mouth_A, mouth_E,
   mouth_O); place instance on layer "MOUTH" frame 1.
5. `set_switch_state("MOUTH", 1, "mouth_E")` → expect firstFrame=1.
6. Verify via `get_graphic_first_frame` (Phase 3f).
7. `apply_auto_lipsync` attempted — non-fatal on error.

**Phase 3h done criteria**: unit tests pass; import_audio +
set_switch_state verified end-to-end; apply_auto_lipsync either
verified or documented as deferred. Wall time ~130-180s.

---

### Phase 3i — Camera + render tools

**Status:** In progress (2026-05-16)

**Ships:**

- `tools/camera.py` with **3 MCP tools** (combined into one
  module — render.py merged):
  - `set_camera_position(fla_path, frame, x, y, zoom, rotation)` —
    experimental; sets Animate's Camera layer transform at the
    given frame. JSFL surface for the Camera (added CC 2018) is
    sparse; this ships as best-effort.
  - `render_to_mp4(fla_path, out_path, fps)` — renders the full
    timeline to an MP4. Two-stage: (a) JSFL exports the timeline
    as a PNG sequence to a temp dir, (b) Python uses
    imageio-ffmpeg to encode the PNGs to MP4 at the specified
    FPS. This avoids depending on Animate's native MP4 codec
    licensing.
  - `render_preview(fla_path, out_path, start_frame, end_frame, fps)`
    — same shape as `render_to_mp4` but renders only the
    specified frame range. Useful for quick orchestrator
    verification without waiting for the full timeline.

**JSFL templates** in `mcp_server/jsfl_templates/`:
- `set_camera_position.jsfl`
- `export_png_sequence.jsfl` (used by both render tools)

**Smoke (`_smoke_phase3i.py`)**:
1. `create_document` + `import_image_as_layer` (something to render).
2. `insert_keyframe` at frame 10 + `set_instance_position` at 10
   (motion to verify).
3. `render_to_mp4` → MP4 created, ≥ 10 frames, > 0 bytes.
4. `render_preview` for frames 1-5 → smaller MP4 created.
5. `set_camera_position` attempted on frame 1 — experimental, non-fatal.

**Phase 3i milestone**: the MCP server becomes feature-complete
enough to build a real shot manually (without Node 6/7 yet). 
Phase 3l (orchestrator) will then call these in sequence on real
animatic data.

**Phase 3i done criteria**: unit tests pass; render_to_mp4 +
render_preview both produce playable MP4s; set_camera_position
either verified or documented as experimental. Wall time
~150-220s.

---

### Phase 3j — Per-frame pose estimation (Node 6)

**Status:** In progress (2026-05-16)

**Scope decision**: ship the FRAMEWORK + a mock backend + an HTTP
client backend now. Defer the real DWPose local install (heavy:
PyTorch + ONNX runtime + ~1 GB weights) to a future fixup OR have
the operator install on a RunPod worker behind the HTTP backend.

**Ships:**

- `pipeline/__init__.py` — new package for pipeline Nodes (parallel
  to mcp_server). Each pipeline Node is its own module.
- `pipeline/errors.py` — Node6Error hierarchy following the prior
  project's convention.
- `pipeline/schemas.py` — pydantic models for:
  - `Joint` (x, y, confidence)
  - `JointSet` (17 named joints per RIG_SPEC_v1)
  - `CharacterPose` (identity + bbox + JointSet)
  - `FramePoseSet` (frame index + list of CharacterPose)
  - `PoseMap` (schemaVersion 1, shotId, frames dict)
  - `ShotPoseSummary` + `Node6Result` (aggregate)
- `pipeline/pose_estimator.py` — abstract `PoseEstimator` interface
  with `estimate_pose(image, bbox) -> JointSet` method.
- `pipeline/pose_backends/`:
  - `mock.py` — returns synthetic poses (deterministic from bbox)
    for testing + as orchestrator stub.
  - `http_client.py` — POSTs frames + bboxes to a remote pose
    service (the RunPod worker the operator deploys).
- `pipeline/cli_node6_pose.py` — CLI that reads node5_result.json
  + per-shot frames, calls the chosen backend, writes pose_map.json
  per shot + node6_result.json aggregate.
- `run_node6_pose.py` — repo-root wrapper with sys.path fixup (same
  pattern as the prior project's run_node*.py).
- `tests/test_node6_pose.py` — schema validation, mock backend,
  HTTP client mock, CLI smoke on synthetic data.

**Deferred (operator-time tasks, documented for handover)**:

- `pipeline/pose_backends/dwpose_local.py` — local DWPose. Requires
  torch + onnxruntime + 1 GB weights. Operator opts in by installing
  the optional deps + running `--backend dwpose_local`.
- RunPod HTTP service deployment — operator runs a small FastAPI
  app exposing `/estimate_pose` on RunPod with GPU. Phase 3j
  documents the HTTP contract; the actual deployment is operator's.

**JSON schemas**:

```
pose_map.json:
  schemaVersion: 1
  shotId: str
  frames: { "1": FramePoseSet, "2": ..., ... }

FramePoseSet:
  frameIndex: int
  characters: [CharacterPose, ...]

CharacterPose:
  identity: str
  bbox: { x, y, w, h }
  joints: {
    "nose": { x, y, confidence },
    "neck": { x, y, confidence },     # computed from shoulders if needed
    "shoulder_L": ..., "shoulder_R": ...,
    "elbow_L": ..., "elbow_R": ...,
    "wrist_L": ..., "wrist_R": ...,
    "hip_L": ..., "hip_R": ...,
    "knee_L": ..., "knee_R": ...,
    "ankle_L": ..., "ankle_R": ...
  }

node6_result.json:
  schemaVersion: 1
  shots: [ShotPoseSummary, ...]

ShotPoseSummary:
  shotId: str
  framesProcessed: int
  charactersFound: int
  poseMapPath: str (absolute)
```

**HTTP backend contract** (for the RunPod worker the operator runs):

```
POST /estimate_pose
Content-Type: multipart/form-data
Body:
  image_frame:  PNG file (the cropped character region)
  bbox: JSON { x, y, w, h }
  expected_identity: str (optional, for logging)

Response 200:
  Content-Type: application/json
  {
    "joints": {
      "nose": { x, y, confidence },
      ...
    },
    "model": "dwpose-v1",
    "infer_time_ms": int
  }

Response 4xx/5xx → CLI logs warning, sets character's pose to null
in the output, continues processing.
```

**Phase 3j done criteria**: tests pass on synthetic data; CLI runs
end-to-end with the mock backend producing valid `pose_map.json`.
HTTP backend has unit tests that mock urllib responses. Wall time:
pure-Python, no Animate, ~5-10 sec for a full test run.

---

### Phase 3k — Pose → bone angle math

**Status:** In progress (2026-05-16)

**Scope** (placed under `pipeline/` not `orchestrator/` — the
original roadmap predates the `pipeline/` package naming decided
in Phase 3j):

- `pipeline/pose_to_bones.py` with:
  - `RigSpec` dataclass — subset of the rig's `_metadata` JSON
    relevant to pose-to-bones math (height, shoulder width, head
    pivot offset, rotation strip frame count + angle step).
  - `compute_bone_angle(parent_joint, child_joint) -> float | None`
    helper — atan2-based angle in degrees, Animate stage convention.
  - `compute_bone_angles_from_pose(pose, rig_spec) -> dict[str, float | None]`
    — returns angle per named bone (`bone_arm_L_upper`,
    `bone_arm_R_lower`, etc.). None for bones whose joints are
    missing/low-confidence.
  - `angle_to_rotation_strip_frame(angle_degrees, frame_count,
    angle_step) -> int` — maps continuous angle to discrete
    rotation-strip frame index 0..frame_count-1.
  - `compute_rig_position(pose, rig_spec) -> tuple[float, float] | None`
    — head-anchored: rig origin = nose_pos − head_pivot_offset.
    Returns None if pose has no nose joint.
  - `compute_rig_scale(pose, rig_spec) -> float | None`
    — shoulder-width based: scale = pose_shoulder_width /
    rig_default_shoulder_width. Returns None if either shoulder is
    missing or default width is invalid.

- `pipeline/__init__.py` updated to re-export the public API.

- Tests in `animate_cc_pipeline/tests/test_pose_to_bones.py`:
  - Angle math on synthetic joint pairs at known orientations
    (horizontal = 0°, vertical down = 90°, etc.).
  - Missing-joint handling.
  - Rotation strip mapping correctness (0° → frame 0, 45° → frame 1,
    90° → frame 2, etc., wraparound).
  - Position + scale math on synthetic poses.

**No Animate, no real pose model.** Pure-Python; tests run in
seconds. ~20 unit tests.

**Phase 3k done criteria**: all unit tests pass. The math is wired
up for the orchestrator (Phase 3l) to call.

---

### Phase 3l — Orchestrator end-to-end (Node 7)

**Status:** In progress (2026-05-16)

**Scope** (relocated to `pipeline/orchestrator/` to fit the
package layout established in Phase 3j):

- `pipeline/orchestrator/` — new sub-package.
- `pipeline/orchestrator/assembly_schemas.py` — pydantic schemas:
  - `CharacterConfig` (identity, rig_fla_path OR placeholder_image_path)
  - `ShotConfig` (per-shot inputs)
  - `ShotAssembly` (per-shot output report)
  - `AssemblyReport` (aggregate across all shots in a batch)
- `pipeline/orchestrator/shot_processor.py` — `process_shot(config)`
  applies the recipe established by Phases 3c-3k:
  1. create_document
  2. import animatic reference video (rough MP4)
  3. import background image
  4. for each character:
     a. import rig OR place placeholder image
     b. for each keypose frame in pose_map:
        - compute_rig_position + compute_rig_scale + bone_angles
        - apply via set_instance_position / set_instance_scale +
          set_graphic_first_frame per bone
        - insert_keyframe
     c. add classic tween between consecutive keyframes
  5. import audio + apply_auto_lipsync (best-effort)
  6. save_document
  7. render_to_mp4
  Returns a `ShotAssembly` with success flag + paths + per-step
  timings + any soft-fail warnings.
- `pipeline/orchestrator/cli_node7_animate.py` — CLI that drives
  `process_shot` over a list of shots from the inputs.
- `run_node7_animate.py` — repo-root wrapper.
- Unit tests in `tests/test_orchestrator.py` — exercise
  `process_shot` with **mocked MCP handlers** so they don't actually
  launch Animate. Covers per-step ordering, error propagation, and
  the assembly report shape.
- End-to-end smoke `tests/_smoke_phase3l.py` — uses **real** MCP
  handlers with **synthetic inputs**: PIL-generated background +
  PIL-generated character "placeholder image" (instead of rig) +
  mock-backend-derived pose_map. Verifies the full chain produces
  a real MP4 with the expected frame count.

**Deferred (operator handover / later phases)**:

- Real TMKOC end-to-end: blocked on rigger commission (Phase 3o).
- Multi-character z-order beyond `bbox.bottom_y`: keep simple ordering
  for v1.
- Camera move detection from rough animatic: Phase 3m.
- Real lipsync: `apply_auto_lipsync` ships in the recipe but is
  best-effort (per the experimental flag from Phase 3h).

**Phase 3l done criteria**: unit tests pass on mocked handlers;
smoke produces a real MP4 from synthetic data (placeholder image
moves across the canvas over several frames). The orchestrator code
is wired up to all 26 MCP tools + the pose-math module from 3k.
Wall time ~140-180s for smoke (8-10 Animate launches).

---

### Phase 3m — Camera move detection

**Status:** **Shipped 2026-05-17** (commit `21b9886`)

**Scope** (tight — keeps the pipeline simple):

- `pipeline/camera_detector.py`:
  - `CameraState` pydantic model: per-frame camera transform
    (cumulative x, y, zoom, rotation, confidence).
  - `CameraMovesMap` pydantic model: schemaVersion + shot_id +
    list of CameraState entries.
  - `detect_translation(frame_a, frame_b) -> tuple[float, float, float]`
    — uses `cv2.phaseCorrelate` on grayscale float32 frames.
    Returns `(dx, dy, confidence)`.
  - `detect_camera_moves_from_frames(frame_paths, shot_id)` —
    pairs consecutive frames, accumulates deltas, returns
    CameraMovesMap.
- `pipeline/cli_camera_detector.py` — CLI: takes a frames dir,
  writes camera_moves.json.
- `run_camera_detect.py` — repo-root wrapper.
- `tests/test_camera_detector.py` — synthetic frame tests with
  known shifts (np.roll), confidence sanity checks, accumulation
  correctness.

**Deferred (Phase 3m-fixup or 3n)**:

- Zoom + rotation detection — harder + less critical for sitcom
  content (mostly pans). Translation alone covers ~80% of TMKOC
  camera moves. The CameraState model already has zoom + rotation
  fields with defaults so future detection backends can populate
  them.
- Orchestrator integration — ShotConfig.camera_moves_path +
  shot_processor calling set_camera_position per frame. Ships
  alongside the production batch runner (Phase 3n).

**Phase 3m done criteria**: detection module produces correct
translations on synthetic shifted-frame pairs; CLI writes a valid
camera_moves.json. Pure-Python module, no Animate. ~15 unit tests.

---

### Phase 3n — Production batch runner

**Status:** **Shipped 2026-05-17** (this commit)

**Scope** (operator-facing batch driver + camera-move integration
deferred from Phase 3m):

- Extended `ShotConfig` with `camera_moves_path: Optional[Path]`.
- Extended `shot_processor` to read camera_moves.json and call
  `set_camera_position` per frame (`_apply_camera_moves` step
  inserted between character processing and audio).
- `pipeline/batch_runner.py`:
  - `BatchProgress` schema (single JSONL line per attempt).
  - `BatchReport` schema (final aggregate).
  - `run_batch(shots, retry_count, jsonl_path, rig_spec)
    -> BatchReport` — sequential per-shot processor with retry +
    append-mode JSONL log.
- `pipeline/cli_batch.py` — CLI with `--retry-count` + `--jsonl`
  flags.
- `run_batch.py` — repo-root wrapper.
- `tests/test_batch_runner.py` — ~15 tests on retry policy,
  JSONL format, aggregate counts, CLI smoke.

**Deferred**:

- In-line pose / camera detection: operator runs the dedicated
  CLIs (`cli_node6_pose`, `cli_camera_detector`) as preprocessing.
- Prior-project Nodes 2-5 chaining: those live in the
  `animatic-refinement` repo; operator runs them separately.

---

### Phase 3o — First real-rig validation (Jethalal)

**Status:** Pending

**Ships:**

- A real Jethalal rig built by a freelance rigger conforming to
  `RIG_SPEC_v1`
- Rig validator passes on Jethalal
- End-to-end pipeline run on a real TMKOC shot featuring Jethalal
- Identifies + documents any rig-contract gaps (e.g., mouth state
  names that need adjusting); fixup phase if needed

**Phase 3o is gated on operator's rigger delivering the rig.**

---

### Phase 3p — Documentation pass + first real episode test

**Status:** Pending

**Ships:**

- All six canonical files cross-checked and synced
- `tools/phase3/validate_phase3_env.py` written and used to test
  pipeline bringup on a clean machine
- First real 22-min episode processed end-to-end
- Per-episode metrics: wallclock, animator-touchup-time, cost
- Production-readiness sign-off in CLAUDE.md status table

---

## Estimated time per phase

Most phases are 1-3 days of focused work. Phases 3f, 3l, 3o, 3p
are bigger (3-7 days each because they integrate previous work).

**Total estimate: 6-10 weeks at one-phase-at-a-time pace, single
operator with Claude Code.**

Bigger team can parallelize 3c/3d/3e/3g (they're independent MCP
tools) — could compress to 4-6 weeks.

## What this roadmap deliberately does NOT cover

- **Rigging the production cast** (24+ characters beyond Jethalal).
  Belongs to a separate "Phase 4" effort once Phase 3 proves the
  pipeline. Each subsequent rig is a v2-track ship.
- **Building backgrounds for production.** Out of scope for Phase 3.
  Phase 3 uses placeholder backgrounds.
- **Voice / dialogue production.** Pipeline accepts WAVs; producing
  them (TTS vs voice actors) is a separate operator decision.
- **Editor workflow / final delivery format.** Pipeline outputs draft
  MP4; the editor's tools and color/grading workflow are out of scope.
- **Client pitch deck / business documents.** Marketing material is
  not in this repo.
