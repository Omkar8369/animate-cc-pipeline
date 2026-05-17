# MCP Server — Animate CC bridge

Python MCP server that exposes Adobe Animate CC operations as tools
Claude Code can call. Implements the Model Context Protocol.

## How it works

For every tool call:

1. Claude Code sends an MCP request with tool name + parameters
2. `server.py` routes to the appropriate `tools/<category>.py`
3. The tool function:
   - Generates a parameterized JSFL script from a template in
     `jsfl_templates/`
   - Writes it to a temp file
   - Spawns `Animate.exe -AlwaysRunJSFL <script.jsfl>`
   - Reads result from a designated output JSON / image / video
   - Returns to Claude as the MCP response
4. Claude sees the result and decides the next action

## Animate.exe lifecycle (notes from Phase 3b debugging)

**Animate does NOT reliably exit on its own.** The Phase 3b spike
turned up multiple ways `Animate.exe -AlwaysRunJSFL <script>` can
"complete the work but stay running":

1. **`fl.quit()` is unreliable.** Animate 2020 shows a Welcome
   screen / "save changes?" dialog / Creative Cloud sign-in that
   silently blocks the quit. JSFL completes, but Animate.exe stays
   resident at ~500 MB.
2. **`fl.closeDocument(doc, false)` only closes the document pane**,
   not the app.
3. **Single-instance behavior.** If Animate.exe is already running
   when we invoke `Animate.exe -AlwaysRunJSFL <script>`, the second
   process delegates to the existing instance and exits
   immediately — but the existing instance may or may not run the
   JSFL depending on its state.

So Phase 3b's `jsfl_bridge.run_jsfl_template` treats Animate as a
**deterministic black-box renderer**:

1. Force-kill any existing `Animate.exe` first (avoids the
   delegation failure mode). Controlled by `kill_existing_first=True`.
2. Launch Animate.exe via `subprocess.Popen` (non-blocking).
3. Wait `boot_grace` seconds (default 5s) for Animate to boot.
4. Poll filesystem for `expected_outputs` to appear (plus a
   sentinel file the JSFL writes after its work). Polling interval
   default 0.5s; timeout default 180s.
5. Once all expected outputs exist, force-kill Animate.exe via
   `taskkill /F /T /IM Animate.exe`.
6. Return a `JsflResult` with `completed_normally=True` if all
   outputs landed.

This pattern doesn't depend on Animate ever exiting. The smoke
typically lands the .fla + sentinel in ~15-25 seconds on a warm
machine, including cold-boot of Animate.

### Other gotchas discovered

- **`fl.saveDocument(doc, fileURI)` vs `fl.saveDocumentAs(doc, fileURI)`.**
  The two functions look interchangeable in the Adobe docs but
  behave differently in Animate 2020:
  - `fl.saveDocument(doc, URI)` → saves directly to URI. Returns
    boolean. **This is what we use.**
  - `fl.saveDocumentAs(doc, URI)` → IGNORES the URI parameter and
    opens the interactive Save-As dialog. Hangs JSFL forever.
- **Layer ops are on `Timeline`, NOT `Document`.** `doc.addNewLayer`
  does not exist in Animate 2020 — calling it raises `TypeError:
  doc.addNewLayer is not a function`. Use:
  ```javascript
  doc.getTimeline().addNewLayer(name, layerType);
  ```
  Same for `insertBlankKeyframe`, `currentFrame`, etc. — they live
  on the Timeline object retrieved via `doc.getTimeline()`.
  Discovered in Phase 3c.
- **`FLfile.platformPathToURI` returns Mac-style URIs** with `C|`
  instead of `C:` (e.g., `file:///C|/path/to/file.fla`). This is
  Adobe's legacy URI format from Flash. Looks weird but works.
- **JSFL scripts run in the system temp dir (e.g.,
  `C:\Users\OMKARH~1\AppData\Local\Temp\animate_mcp_*.jsfl`).** The
  8.3 short name is fine; spaces in user-profile paths are
  handled correctly by `FLfile.platformPathToURI`.

### Capture behavior

- **stdout/stderr is typically empty.** Animate writes to its own
  Output Panel (Window → Output), not the parent process's stdout.
  The bridge doesn't rely on captured output as a success signal —
  filesystem outputs are the contract.
- **Exit code is not a reliable success signal.** We don't even let
  Animate exit on its own; the bridge force-kills it after outputs
  appear. The `JsflResult.exit_code` is `None` for the polling path.

### Path conventions

Animate CC's JSFL `fl.saveDocumentAs` (and most `fl.*` document
ops) expect **file:// URI paths** with forward slashes, not Windows
backslash paths:

```jsfl
// WRONG: fl.saveDocumentAs(doc, "C:\\path\\to\\file.fla");  // may fail
// RIGHT:
var uri = FLfile.platformPathToURI("C:/path/to/file.fla");
fl.saveDocumentAs(doc, uri);
```

JSFL templates in `jsfl_templates/` use `FLfile.platformPathToURI()`
to convert. Python callers should pass forward-slash paths in
substitutions to avoid double-escaping headaches.

### Long-lived instance reuse (deferred)

For Phase 3b each tool call spawns a fresh `Animate.exe` and the
bridge kills it after outputs land. Cold-boot is ~15-25s. A future
phase (likely Phase 3c or 3i) will keep a single Animate instance
alive across many JSFL invocations using a "command queue file"
pattern: Python writes JSFL scripts to a watched folder; a
long-running JSFL polling loop inside Animate picks them up. Until
then, batch operations carefully — don't make N tool calls when one
larger JSFL script can do the work.

### Known gotchas

- **First-launch dialogs.** A fresh Animate install may pop dialogs
  ("Welcome", license activation, tour). Run Animate manually once
  to dismiss them before relying on `-AlwaysRunJSFL`.
- **Modal dialogs hang JSFL.** If a script triggers an error dialog
  (e.g., "Cannot save: read-only"), JSFL pauses waiting for user
  click. The Python force-kill catches this — the bridge times out
  and kills Animate, returning `completed_normally=False` with the
  missing outputs reported.
- **Animate locks the .fla while open.** Closing with
  `fl.closeDocument(doc, false)` releases the lock so Python can
  read the file after.
- **Sentinel writes happen LAST in the JSFL.** Always write the
  sentinel after the real output is on disk. Python's poll loop
  waits for ALL expected outputs (the .fla AND the sentinel) before
  killing Animate, so the order in JSFL is: do work → save outputs →
  write sentinel → `fl.quit()` (best-effort).

## Configuration

MCP server reads these env vars (set in `.claude/settings.json`):

- `ANIMATE_CC_EXE` — path to `Animate.exe`. Default:
  `C:\Program Files\Adobe\Adobe Animate 2020\Animate.exe`
- `ANIMATE_TEMP_DIR` — where JSFL scripts + outputs are buffered.
  Default: system temp dir
- `ANIMATE_LOG_LEVEL` — `debug` / `info` / `warn` / `error`. Default
  `info`

## Tool categories

| File | Phase | Tools |
|------|-------|-------|
| `tools/document.py` | **3c + 3o-code (shipped)** | create_document, save_document, close_document, import_image_as_layer, import_video_as_layer, import_character_rig (3o-code) |
| `tools/symbol.py` | **3d (shipped)** | place_symbol_instance, set_instance_position, set_instance_scale, set_instance_rotation |
| `tools/keyframe.py` | **3e (shipped, partial)** | insert_keyframe, insert_blank_keyframe, get_keyframes, remove_keyframe (deferred — Animate 2020 hangs on clearKeyframes) |
| `tools/bone.py` | **3f (shipped, partial)** | set_graphic_first_frame, get_graphic_first_frame, validate_rig; armature-bone tools (list_bones, set_bone_angle, set_bone_position) deferred to Phase 3f-fixup pending real rig |
| `tools/tween.py` | **3g (shipped)** | add_classic_tween, add_motion_tween, set_easing — all 3 verified end-to-end |
| `tools/audio.py` | **3h (shipped)** | import_audio, set_switch_state, apply_auto_lipsync — all 3 verified (apply_auto_lipsync marked experimental — runs without errors but Hindi-audio quality unverified) |
| `tools/camera.py` | **3i (shipped)** | set_camera_position (experimental), render_to_mp4, render_preview — all 3 verified end-to-end. Render uses two-stage PNG sequence + imageio-ffmpeg encode. Phase 3i merges the original `tools/render.py` plan into `tools/camera.py`. |

Plus utilities (later phases): `get_stage_info`, `list_library_symbols`,
`list_layers`, `validate_rig_against_spec`.

### Phase 3c shipped tools (in detail)

| Tool | Action | Spawns Animate? | Wall time |
|------|--------|-----------------|-----------|
| `create_document(fla_path, width, height, fps)` | New empty .fla at canvas dimensions | Yes | ~20s |
| `save_document(fla_path)` | Open existing .fla, save, close (integrity round-trip) | Yes | ~18s |
| `close_document()` | Force-kill any running Animate.exe | No | <1s |
| `import_image_as_layer(fla_path, image_path, layer_name, frame)` | Add layer + place PNG/JPG | Yes | ~17s |
| `import_video_as_layer(fla_path, mp4_path, layer_name, frame)` | Add layer + embed MP4 | Yes | ~20-30s (slower for long videos) |

All Animate-spawning tools follow the bridge's sentinel-polling +
force-kill pattern from Phase 3b. Each tool is stateless — opens
.fla, performs one operation, saves, closes. Long-running Animate
instance reuse is deferred to Phase 3i.

### Phase 3o-code shipped tool (in detail)

| Tool | Action | Wall time |
|------|--------|-----------|
| `import_character_rig(fla_path, rig_fla_path, identity, layer_name, frame, x, y)` | Import the rig .fla's library into the target doc (library-only, no stage placement), add a fresh top-level layer, place an instance of the `identity` MovieClip on the requested frame at (x, y). Per `RIG_SPEC_v1` the rig .fla must contain a MovieClip at library root whose name matches `identity` exactly. | ~25-35s (heavier than single-asset imports — the whole rig library lands in the target doc) |

**Sentinel contract**: the JSFL writes one of three payloads:

- `"done"` — library imported, instance placed (instance_placed=true)
- `"import_failed"` — `doc.importFile` returned false; handler returns status=error
- `"instance_not_placed"` — library imported but `lib.addItemToDocument` couldn't find the identity symbol; handler returns status=ok with a warning + `instance_placed=false` so the orchestrator can skip the character cleanly.

**JSFL approach**: `doc.importFile(uri, true)` is Animate's
library-only import path — it pulls the whole .fla's library into
the target doc without putting anything on stage. We then add a new
layer + convertToKeyframes at the target frame + call
`lib.addItemToDocument({x, y}, identity)` to drop the instance.

Phase 3o-code ships the tool but Phase 3o-validation (gated on
real rigger delivery) is what proves the JSFL works against actual
RIG_SPEC_v1-compliant `.fla` files in the wild.

**Phase 3o-adapter (sidecar identity resolution)**: production rigs
from the operator's rigger use obfuscated library symbol names. The
handler now calls `pipeline.rig_labels.resolve_identity_via_sidecar`
to translate operator-friendly angle labels (`front`, `side_l`,
`back`, ...) to the actual obfuscated library names. The sidecar
file is at `<rig.fla>.labels.json` next to the rig (or wherever a
caller points it). The handler's response payload includes both
`identity_requested` and (resolved) `identity` so the orchestrator
can confirm what was actually imported.

### Phase 3d shipped tools (in detail)

| Tool | Action | Wall time |
|------|--------|-----------|
| `place_symbol_instance(fla_path, symbol_name, layer_name, frame, x, y)` | Place an instance of a library symbol; auto-creates the layer if missing | ~20s |
| `set_instance_position(fla_path, layer_name, frame, x, y)` | Move the first element on (layer, frame) to (x, y) | ~17s |
| `set_instance_scale(fla_path, layer_name, frame, sx, sy)` | Set scaleX/scaleY on the first element on (layer, frame) | ~17s |
| `set_instance_rotation(fla_path, layer_name, frame, angle)` | Set rotation (degrees, CW positive) on the first element | ~17s |

**Identification model**: each modify tool finds its target by
**layer name + frame number** (1-indexed externally, converted to
0-indexed for JSFL). The first element on that (layer, frame) is
the target. Matches the rigging workflow — one rigged character
per layer.

**Transform-order convention (Phase 3d gotcha)**: apply transforms
in this order — **rotation → scale → position**. Position LAST.
JSFL's `element.x` / `element.y` represent the post-transform
bounding-box top-left, which shifts under rotation/scale; setting
position last gives you back exactly what you set. The Phase 3d
smoke verifies this round-trips through save+reopen with ~2px
tolerance.

### Phase 3e shipped tools (in detail)

| Tool | Action | Status |
|------|--------|--------|
| `insert_keyframe(fla_path, layer_name, frame)` | Insert keyframe at frame (inherits prior content). Auto-extends layer if needed. | ✅ Verified |
| `insert_blank_keyframe(fla_path, layer_name, frame)` | Insert blank keyframe at frame. Auto-extends layer. | ✅ Verified |
| `get_keyframes(fla_path, layer_name)` | READ-only: return sorted list of 1-indexed keyframe positions on the layer | ✅ Verified |
| `remove_keyframe(fla_path, layer_name, frame)` | Clear keyframe status (extend from prior). | ⚠️ Deferred — see gotcha #5 |

**JSFL keyframe insertion approach**: Phase 3e settled on
`Timeline.setSelectedLayers(idx) → Timeline.currentLayer = idx →
Timeline.insertFrames(...)` to extend if needed →
`Timeline.convertToKeyframes(start, end)` (or `convertToBlankKeyframes`
for the blank variant). This pattern is more reliable than
`Timeline.insertKeyframe(N)` which silently no-ops in some
configurations.

### Phase 3f shipped tools (in detail)

| Tool | Action | Status |
|------|--------|--------|
| `set_graphic_first_frame(fla_path, layer_name, frame, target_first_frame, loop_mode)` | Pin a Graphic Symbol instance to a specific frame of its underlying timeline (the rotation-strip primitive). Loop modes: `loop`, `play once`, `single frame` (default). | ✅ Verified |
| `get_graphic_first_frame(fla_path, layer_name, frame)` | READ-only — return firstFrame + loop + instanceType of the element on (layer, frame). | ✅ Verified |
| `validate_rig(fla_path, identity)` | Run rig_validator against a .fla. Returns JSON report with per-rule pass/fail + structured error messages. Used by orchestrator to gate rig ingestion. | ✅ Verified (negative path) |

**Pragmatic scope (deferred to Phase 3f-fixup or Phase 3o):**
`list_bones`, `set_bone_angle`, `set_bone_position` — all require an
armature-rigged `.fla` to test against; JSFL `addNewArmature` is
rough; Animate's Bone tool is interactive-only. Will land alongside
real rigger commission.

**`rig_contracts/rig_validator.py`** (Python module, not an MCP tool
directly — exposed via `validate_rig` MCP tool):
Checks against RIG_SPEC_v1 — root MovieClip name, required layers,
mouth/eye/eyebrow/face switch states, rotation-strip frame counts,
`_metadata` JSON shape + identity match. Returns
`ValidationReport` with per-rule `CheckResult`s. Pure-Python; unit
tests run synthetic structure JSON inputs.

### Phase 3g shipped tools (in detail)

| Tool | Action | Status |
|------|--------|--------|
| `add_classic_tween(fla_path, layer_name, start_frame)` | Add Classic Tween starting at keyframe. Animate interpolates position/rotation/scale to next keyframe. Via `Timeline.createMotionTween()` (NOT direct `frame.tweenType =` which is read-only). | ✅ Verified |
| `add_motion_tween(fla_path, layer_name, start_frame, end_frame)` | Create modern Motion Tween span via `Timeline.createMotionObject`. Tagged experimental, but verified working on Animate 2020. | ✅ Verified |
| `set_easing(fla_path, layer_name, frame, easing)` | Set tweenEasing on starting keyframe of a tween. Range -100 (ease-in) to +100 (ease-out). Via `Timeline.setFrameProperty("tweenEasing", N, start, end)` (NOT direct assignment which silently no-ops). | ✅ Verified |

**Phase 3g gotchas (two new ones)**:

- **`Frame.tweenType` is read-only** in JSFL. Direct assignment
  silently no-ops. Use `Timeline.createMotionTween()` after
  selecting the layer + setting current frame to the starting
  keyframe.
- **`Frame.tweenEasing` direct assignment silently no-ops** despite
  docs claiming it's read/write. The right setter is
  `Timeline.setFrameProperty("tweenEasing", N, startFrame,
  endFrame)`. Frame objects in JSFL appear to be immutable views
  for tween properties.

### Phase 3h shipped tools (in detail)

| Tool | Action | Status |
|------|--------|--------|
| `import_audio(fla_path, audio_path, layer_name, frame)` | Import WAV/MP3/AIFF + place on a layer at a frame. Auto-creates layer. | ✅ Verified (44KB WAV → .fla grew 3.8KB → 90KB) |
| `set_switch_state(fla_path, layer_name, frame, state_name)` | Pin a Switch-style Graphic Symbol to its frame labeled `state_name`. Used for mouth shapes + facial expressions. | ✅ Verified (state-name → firstFrame lookup works) |
| `apply_auto_lipsync(fla_path, audio_layer, mouth_layer)` | Experimental — attempt Animate's Auto Lip Sync. Runs without errors but quality on Hindi audio is unverified. Use per-frame `set_switch_state` as fallback if needed. | ⚠️ Experimental (runs clean, quality TBD) |

### Phase 3i shipped tools (in detail)

| Tool | Action | Status |
|------|--------|--------|
| `set_camera_position(fla_path, frame, x, y, zoom, rotation)` | EXPERIMENTAL. Sets Camera layer transform at frame. Animate's Camera JSFL surface is sparse; ships with try/catch around each setter. | ⚠️ Experimental (runs clean) |
| `render_to_mp4(fla_path, out_path, fps)` | Renders full timeline to MP4. JSFL exports PNG sequence to temp dir; Python encodes via imageio-ffmpeg (libx264 + yuv420p). | ✅ Verified (10-frame test → 2046-byte MP4) |
| `render_preview(fla_path, out_path, start_frame, end_frame, fps)` | Same pipeline but for a frame range. Used for quick verification + per-shot preview. | ✅ Verified (5-frame test → 1783-byte MP4) |

**Render pipeline notes**:

- **Two-stage**: JSFL loop iterates frames + calls `doc.exportPNG(uri, true, true)` per frame to write `frame_NNNN.png` to a temp directory.
- **Python encoder**: uses `imageio_ffmpeg.get_ffmpeg_exe()` to invoke ffmpeg with `-framerate <fps> -i pattern -c:v libx264 -pix_fmt yuv420p -vf pad=ceil(iw/2)*2:ceil(ih/2)*2`. The pad filter ensures even dimensions (libx264 requirement).
- **Fallback**: glob pattern is tried first, then numeric pattern with `-start_number` if glob isn't supported on the platform's ffmpeg.
- **Cleanup**: temp PNG directory is removed after encoding regardless of success/failure.

This approach decouples our render pipeline from Animate's native MP4 codec licensing (which varies by version + tier) — we just need a working PNG export from Animate and libx264 from imageio-ffmpeg.

### Phase 3e gotcha #5 — clearKeyframes hangs in Animate 2020

`Timeline.clearKeyframes(start, end)` AND the selection-based form
`setSelectedFrames + clearKeyframes()` both hang JSFL on Animate
2020 — likely behind an undismissable confirmation dialog. The
bridge times out at 180s and force-kills Animate; the .fla is left
unmodified.

The `remove_keyframe` tool is shipped with this caveat in its
description. Smoke skips its live verification. Likely works in
Animate 2022+ (when we test that, the smoke can be flipped back
on); for now the orchestrator (Phase 3l) plans an insert-heavy
pipeline so this is acceptable for v1.

## JSFL templates

`jsfl_templates/` contains the per-operation JSFL scripts.
Parameters are substituted via Python string formatting before
writing to temp file. Templates are kept readable JSFL — operator
can debug by running a generated `.jsfl` directly in Animate's
"Run Script" menu.

Naming convention: one template per major operation,
`<verb>_<noun>.jsfl` (e.g., `open_new_doc.jsfl`, `place_symbol.jsfl`,
`render_mp4.jsfl`).

## Running the MCP server

After installation (Phase 3p ships `install_animate_mcp.py`):

```bash
# Auto-started by Claude Code via .claude/settings.json
# Manual launch for testing:
python -m animate_cc_pipeline.mcp_server.server
```

Server listens on stdio (standard MCP transport).

## Testing

`tests/test_mcp_server.py` and `tests/_smoke_animate_cc.py` exercise
the full stack. Dry-run mode (no actual Animate.exe spawn) for unit
tests; integration tests require Animate installed.

## Phase status

See `docs/PHASE_3_ROADMAP.md`. As of Phase 3a, this directory is
empty scaffolding — Phase 3b adds the first real code (`server.py`
+ `jsfl_bridge.py`).
