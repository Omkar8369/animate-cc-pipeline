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

**Status:** Pending

**Ships:**

- `tools/document.py` with:
  - `open_new_document(width, height, fps)`
  - `save_document(path)`
  - `close_document()`
  - `import_animatic_reference(mp4_path, layer_name)`
  - `import_background_image(png_path, layer_name, frame)`
  - `import_character_rig(fla_path)` — imports another `.fla` as
    External Library reference
- JSFL templates: `open_new_doc.jsfl`, `save_doc.jsfl`,
  `import_video.jsfl`, `import_image.jsfl`, `import_fla_library.jsfl`
- Smoke test: create doc with MP4 reference + background + rig
  library, save, reopen, verify structure
- 8-10 unit tests

---

### Phase 3d — Symbol placement tools

**Status:** Pending

**Ships:**

- `tools/symbol.py` with:
  - `place_symbol_instance(symbol, layer, x, y, frame)`
  - `set_instance_position(instance_id, frame, x, y)`
  - `set_instance_scale(instance_id, frame, sx, sy)`
  - `set_instance_rotation(instance_id, frame, angle)`
- Smoke test: place a symbol at 5 positions across 5 frames, save,
  verify positions match
- 6-8 unit tests

---

### Phase 3e — Keyframe tools

**Status:** Pending

**Ships:**

- `tools/keyframe.py` with:
  - `insert_keyframe(layer, frame)`
  - `insert_blank_keyframe(layer, frame)`
  - `remove_keyframe(layer, frame)`
  - `get_keyframes(layer)`
- Smoke test: insert 5 keyframes with different symbol positions,
  render as 5-frame MP4, verify each frame shows the right position
- 6-8 unit tests

---

### Phase 3f — Bone tools + rig contract validator + template rig

**Status:** Pending

**Ships:**

- `tools/bone.py` with:
  - `list_bones(rig_instance)`
  - `set_bone_angle(rig_instance, bone_path, frame, angle)`
  - `set_bone_position(rig_instance, bone_path, frame, x, y)`
  - `set_graphic_first_frame(instance_id, frame_index)`
    *(for rotation strips)*
- `rig_contracts/rig_validator.py` — validates a `.fla` against
  `RIG_SPEC_v1` (checks layer names, bone names, switch states,
  metadata fields)
- `rigs/_template/template_character.fla` — minimal valid placeholder
  rig (stick figure with all required layers/bones/switches; not
  artistically real, but mechanically complete for testing)
- Smoke test: drive the template rig's arm bone across 10 frames at
  varying angles, verify rotation strip swaps correctly
- 10-12 tests

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
