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

**Status:** Pending

**Ships:**

- `tools/tween.py` with:
  - `add_motion_tween(layer, start_frame, end_frame)`
  - `add_classic_tween(layer, start_frame, end_frame)`
  - `set_easing(layer, frame_range, easing_curve)`
- Smoke test: 2 keyframes 30 frames apart, add motion tween,
  render → smooth interpolated motion verified
- 4-6 tests

---

### Phase 3h — Audio + lipsync tools

**Status:** Pending

**Ships:**

- `tools/audio.py` with:
  - `import_audio(audio_path, layer, frame)`
  - `apply_auto_lipsync(audio_layer, mouth_switch_symbol)`
  - `set_switch_state(layer, frame, state_name)`
- Tests against synthetic Hindi WAV file
- Documents which mouth switch states Animate's auto-lipsync targets
  (which determines the `RIG_SPEC_v1` mouth-state name set)
- 6-8 tests

---

### Phase 3i — Camera + render tools

**Status:** Pending

**Ships:**

- `tools/camera.py` with:
  - `set_camera_position(frame, x, y, zoom, rotation)`
- `tools/render.py` with:
  - `render_to_mp4(out_path, fps, range)`
  - `render_preview(start_frame, end_frame)`
- End-to-end smoke: empty doc → place rig → 2 keyframes → tween →
  import audio → auto-lipsync → render MP4 → MP4 plays correctly
  and shows expected motion + audio
- 6-8 tests

**Phase 3i milestone:** the MCP server is feature-complete enough to
build a real shot manually (without Node 6/7 yet).

---

### Phase 3j — Per-frame pose estimation (Node 6)

**Status:** Pending

**Ships:**

- `orchestrator/cli_node6_pose.py` — wraps DWPose
- HTTP API spec for the RunPod worker (since pose runs on cloud GPU)
- `pose_map.json` schema (schemaVersion 1)
- `node6_result.json` aggregate schema
- Tests against synthetic frames + a real TMKOC test frame
- 8-10 tests

---

### Phase 3k — Pose → bone angle math

**Status:** Pending

**Ships:**

- `orchestrator/pose_to_bones.py`:
  - `compute_bone_angles_from_pose(pose, rig_spec) → dict[bone_path → angle]`
  - `compute_rig_position(pose, rig_spec) → (x, y)`
    *(head-anchored)*
  - `compute_rig_scale(pose, rig_spec) → float`
    *(shoulder-width based)*
- Unit tests on synthetic poses (known joint coordinates → known
  bone angles)
- Tests against the Phase 3f template rig

---

### Phase 3l — Orchestrator end-to-end (Node 7)

**Status:** Pending

**Ships:**

- `orchestrator/cli_node7_animate.py`:
  - Reads Node 5 + Node 6 outputs
  - Drives MCP server tool sequence per shot
  - Produces `auto_animated.fla` + `draft.mp4`
- `orchestrator/shot_processor.py` for the per-shot loop
- `animate_assembly.json` manifest schema
- Smoke test on ONE real TMKOC shot using the template rig
- 8-10 tests

---

### Phase 3m — Camera move detection

**Status:** Pending

**Ships:**

- Frame-correlation analysis of rough MP4 → pan/zoom/rotation
  estimates per frame
- Wired into Node 7 → camera keyframes auto-set
- 4-6 tests

---

### Phase 3n — Production batch runner

**Status:** Pending

**Ships:**

- `run_node11_batch.py` (analogous to prior project's `run_node11.py`)
  that chains Node 2 → 3 → 4 → 5 → 6 → 7 for all shots in `queue.json`
- Per-shot retry, JSONL progress log, aggregate `batch_report.json`
- Per-shot wallclock metrics, identifies slowest shots
- 6-10 tests

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
