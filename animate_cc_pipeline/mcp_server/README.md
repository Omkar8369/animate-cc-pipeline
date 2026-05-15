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

## Animate.exe lifecycle (notes from Phase 3b)

JSFL scripts are stateless from Animate's perspective. Each
invocation of `Animate.exe -AlwaysRunJSFL <script.jsfl>` does:

1. Boots Animate.exe (cold launch: ~10-30 seconds on first run,
   ~3-8 seconds on subsequent launches in the same session due to
   warm caches)
2. Loads the specified JSFL script
3. Executes it (synchronously from JSFL's perspective)
4. Exits when the script ends (or stays open if the script opened a
   document and didn't close it)

### Capture behavior

- **stdout/stderr is typically empty.** Animate writes to its own
  Output Panel (Window → Output), not the parent process's stdout.
  Don't rely on captured output as a success signal.
- **Exit code is not a reliable success signal either.** Animate may
  return 0 on JSFL errors or non-zero on JSFL success (depends on
  version and what the script did). The real signal is **whether the
  script's expected side effect happened** (e.g., does the `.fla`
  exist at the expected path? Does the output JSON file have the
  expected schema?).

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

For Phase 3b each tool call spawns a fresh `Animate.exe`. This is
slow (~10s boot per call). A future phase (likely Phase 3c or 3i)
will keep a single Animate instance alive across many JSFL
invocations using one of:

- Animate's built-in `fl.runScript(URI)` JSFL call from inside an
  already-running Animate session (requires AppleEvents / DDE
  hooking)
- A "command queue file" pattern: Python writes JSFL scripts to a
  watched folder; a long-running JSFL polling loop inside Animate
  picks them up
- ExtendScript / ExtendScript Toolkit if compatible

Until then, batch Animate operations carefully — don't make N tool
calls when one larger JSFL script can do the work.

### Known gotchas

- **First-launch dialogs.** A fresh Animate install may pop dialogs
  ("Welcome", license activation, tour). Run Animate manually once
  to dismiss them before relying on `-AlwaysRunJSFL`.
- **Modal dialogs hang JSFL.** If a script triggers an error dialog
  (e.g., "Cannot save: read-only"), JSFL pauses waiting for user
  click. The Python subprocess will hit its timeout. Always design
  JSFL with try/catch + early file-write of an error JSON.
- **Animate locks the .fla while open.** Closing with
  `fl.closeDocument(doc, false)` releases the lock so Python can
  read the file after.

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
| `tools/document.py` | 3c | open_new_document, save_document, close_document, import_animatic_reference, import_background_image, import_character_rig |
| `tools/symbol.py` | 3d | place_symbol_instance, set_instance_position, set_instance_scale, set_instance_rotation |
| `tools/keyframe.py` | 3e | insert_keyframe, insert_blank_keyframe, remove_keyframe, get_keyframes |
| `tools/bone.py` | 3f | list_bones, set_bone_angle, set_bone_position, set_graphic_first_frame |
| `tools/tween.py` | 3g | add_motion_tween, add_classic_tween, set_easing |
| `tools/audio.py` | 3h | import_audio, apply_auto_lipsync, set_switch_state |
| `tools/camera.py` | 3i | set_camera_position |
| `tools/render.py` | 3i | render_to_mp4, render_preview |

Plus utilities: `get_stage_info`, `list_library_symbols`,
`list_layers`, `validate_rig_against_spec`.

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
