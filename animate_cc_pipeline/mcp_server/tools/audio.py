"""Audio + lipsync MCP tools.

Phase 3h: imports audio into the .fla, drives Switch-style Graphic
Symbols by frame-label (mouth shapes, facial expressions), and
attempts Animate's Auto Lip Sync feature.

Tools:
  - import_audio       library import + layer placement
  - set_switch_state   pin Switch Graphic to frame-labeled state
  - apply_auto_lipsync EXPERIMENTAL — Auto Lip Sync via JSFL
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import mcp.types as types

from .. import jsfl_bridge


JSFL_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "jsfl_templates"


# ─── Shared helpers (same pattern as other tool modules) ───────────


def _to_jsfl_path(p: str | Path) -> str:
    return str(p).replace("\\", "/")


def _new_sentinel(near: Path) -> Path:
    return near.with_suffix(near.suffix + ".sentinel")


def _safe_unlink(p: Path) -> None:
    try:
        p.unlink()
    except (OSError, FileNotFoundError):
        pass


def _ok(result: jsfl_bridge.JsflResult, fla_path: Path, extra: dict | None = None) -> str:
    payload: dict[str, Any] = {
        "status": "ok",
        "fla_path": str(fla_path),
        "elapsed_seconds": round(result.elapsed_seconds, 2),
        "completed_normally": result.completed_normally,
    }
    if extra:
        payload.update(extra)
    return json.dumps(payload)


def _err(result: jsfl_bridge.JsflResult, fla_path: Path, message: str) -> str:
    return json.dumps({
        "status": "error",
        "error": message,
        "fla_path": str(fla_path),
        "elapsed_seconds": round(result.elapsed_seconds, 2),
        "missing_outputs": [str(p) for p in result.missing_outputs],
    })


def _check_fla_exists(fla_path: Path) -> list[types.TextContent] | None:
    if not fla_path.exists():
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": f"fla_path does not exist: {fla_path}",
                "fla_path": str(fla_path),
            }),
        )]
    return None


def _check_file_exists(path: Path, label: str) -> list[types.TextContent] | None:
    if not path.exists():
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": f"{label} does not exist: {path}",
            }),
        )]
    return None


# ─── Tool definitions ──────────────────────────────────────────────


IMPORT_AUDIO_TOOL = types.Tool(
    name="import_audio",
    description=(
        "Import an audio file (WAV/MP3/AIFF) into the .fla's library "
        "and place an instance on `layer_name` at `frame`. "
        "Auto-creates the layer if missing. Used for dialogue tracks "
        "(Hindi voice, ambient sound) that the orchestrator places "
        "on its own audio layer. Wall time ~20s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "audio_path": {"type": "string"},
            "layer_name": {"type": "string", "default": "AUDIO"},
            "frame": {"type": "integer", "minimum": 1, "default": 1},
        },
        "required": ["fla_path", "audio_path"],
        "additionalProperties": False,
    },
)


SET_SWITCH_STATE_TOOL = types.Tool(
    name="set_switch_state",
    description=(
        "Pin a Switch-style Graphic Symbol instance to the frame "
        "whose label equals `state_name`. Used for selecting mouth "
        "shapes (e.g. 'mouth_A', 'mouth_E') and facial expressions "
        "(e.g. 'eyebrows_raised', 'expression_angry') per the rig "
        "spec. Internally: opens the instance's library item, finds "
        "the frame labeled `state_name`, sets the instance's "
        "firstFrame to that index + loop='single frame'. If no "
        "frame has that label, the tool returns an error. Wall time "
        "~18s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "layer_name": {"type": "string"},
            "frame": {"type": "integer", "minimum": 1, "default": 1},
            "state_name": {
                "type": "string",
                "description": "Frame label inside the Graphic Symbol's timeline.",
            },
        },
        "required": ["fla_path", "layer_name", "state_name"],
        "additionalProperties": False,
    },
)


APPLY_AUTO_LIPSYNC_TOOL = types.Tool(
    name="apply_auto_lipsync",
    description=(
        "EXPERIMENTAL. Attempt to apply Animate's Auto Lip Sync to "
        "the `audio_layer` and `mouth_layer` of the .fla. Animate's "
        "Auto Lip Sync analyzes phonemes in the audio and sets "
        "mouth-Switch keyframes on the mouth layer. JSFL surface "
        "for this feature is limited; this tool is a best-effort "
        "wrapper. If the operation fails on your Animate version, "
        "fall back to per-frame set_switch_state calls driven by "
        "an external phoneme analyzer (e.g. Papagayo). Wall time "
        "~25-40s depending on audio length."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "audio_layer": {"type": "string"},
            "mouth_layer": {"type": "string"},
        },
        "required": ["fla_path", "audio_layer", "mouth_layer"],
        "additionalProperties": False,
    },
)


ALL_TOOLS: list[types.Tool] = [
    IMPORT_AUDIO_TOOL,
    SET_SWITCH_STATE_TOOL,
    APPLY_AUTO_LIPSYNC_TOOL,
]


# ─── Handlers ──────────────────────────────────────────────────────


async def handle_import_audio(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    audio_path = Path(args["audio_path"])
    layer_name = str(args.get("layer_name", "AUDIO"))
    frame = int(args.get("frame", 1))

    err = _check_fla_exists(fla_path)
    if err:
        return err
    err = _check_file_exists(audio_path, "audio_path")
    if err:
        return err

    sentinel = _new_sentinel(fla_path)
    _safe_unlink(sentinel)

    template = JSFL_TEMPLATES_DIR / "import_audio.jsfl"
    result = jsfl_bridge.run_jsfl_template(
        template,
        substitutions={
            "FLA_PATH": _to_jsfl_path(fla_path),
            "AUDIO_PATH": _to_jsfl_path(audio_path),
            "LAYER_NAME": layer_name,
            "FRAME": frame,
            "SENTINEL_PATH": _to_jsfl_path(sentinel),
        },
        expected_outputs=[sentinel],
        poll_timeout=240.0,
    )
    _safe_unlink(sentinel)

    if not result.completed_normally:
        return [types.TextContent(
            type="text",
            text=_err(result, fla_path,
                      f"import_audio failed for {audio_path}"),
        )]
    return [types.TextContent(
        type="text",
        text=_ok(result, fla_path, {
            "audio_path": str(audio_path),
            "layer_name": layer_name,
            "frame": frame,
        }),
    )]


async def handle_set_switch_state(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    layer_name = str(args["layer_name"])
    frame = int(args.get("frame", 1))
    state_name = str(args["state_name"])

    err = _check_fla_exists(fla_path)
    if err:
        return err

    sentinel = _new_sentinel(fla_path)
    _safe_unlink(sentinel)

    template = JSFL_TEMPLATES_DIR / "set_switch_state.jsfl"
    result = jsfl_bridge.run_jsfl_template(
        template,
        substitutions={
            "FLA_PATH": _to_jsfl_path(fla_path),
            "LAYER_NAME": layer_name,
            "FRAME": frame,
            "STATE_NAME": state_name,
            "SENTINEL_PATH": _to_jsfl_path(sentinel),
        },
        expected_outputs=[sentinel],
        poll_timeout=180.0,
    )
    _safe_unlink(sentinel)

    if not result.completed_normally:
        return [types.TextContent(
            type="text",
            text=_err(result, fla_path,
                      f"set_switch_state({layer_name!r}, frame={frame}, state={state_name!r}) failed"),
        )]
    return [types.TextContent(
        type="text",
        text=_ok(result, fla_path, {
            "layer_name": layer_name,
            "frame": frame,
            "state_name": state_name,
        }),
    )]


async def handle_apply_auto_lipsync(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    audio_layer = str(args["audio_layer"])
    mouth_layer = str(args["mouth_layer"])

    err = _check_fla_exists(fla_path)
    if err:
        return err

    sentinel = _new_sentinel(fla_path)
    _safe_unlink(sentinel)

    template = JSFL_TEMPLATES_DIR / "apply_auto_lipsync.jsfl"
    result = jsfl_bridge.run_jsfl_template(
        template,
        substitutions={
            "FLA_PATH": _to_jsfl_path(fla_path),
            "AUDIO_LAYER": audio_layer,
            "MOUTH_LAYER": mouth_layer,
            "SENTINEL_PATH": _to_jsfl_path(sentinel),
        },
        expected_outputs=[sentinel],
        poll_timeout=300.0,
    )
    _safe_unlink(sentinel)

    if not result.completed_normally:
        return [types.TextContent(
            type="text",
            text=_err(result, fla_path,
                      "apply_auto_lipsync did not complete (experimental — may need fixup)"),
        )]
    return [types.TextContent(
        type="text",
        text=_ok(result, fla_path, {
            "audio_layer": audio_layer,
            "mouth_layer": mouth_layer,
            "note": "experimental — manual verification recommended",
        }),
    )]


TOOL_HANDLERS = {
    "import_audio": handle_import_audio,
    "set_switch_state": handle_set_switch_state,
    "apply_auto_lipsync": handle_apply_auto_lipsync,
}
