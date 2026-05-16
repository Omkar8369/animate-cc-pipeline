"""Bone / rig MCP tools.

Phase 3f shipped scope (pragmatic — see PHASE_3_ROADMAP.md
"Scope revision rationale"):

  - set_graphic_first_frame  — rotation-strip control
  - get_graphic_first_frame  — read helper
  - validate_rig             — runs rig_validator.py against a .fla

Deferred to a future fixup:

  - list_bones / set_bone_angle / set_bone_position
    (need a real armature-rigged .fla to test against; JSFL armature
    creation is rough; Animate's Bone tool is interactive-only)

Rationale: RIG_SPEC_v1 decision #6 uses rotation strips on Graphic
Symbols (not raw bones) as the Smart-Bone substitute for Animate
2020. The orchestrator's per-frame transform updates primarily
drive `graphic.firstFrame` to switch which limb drawing shows.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import mcp.types as types

from .. import jsfl_bridge
from ...rig_contracts import rig_validator


JSFL_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "jsfl_templates"


# ─── Shared helpers (mirror document.py / symbol.py / keyframe.py) ─


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


# ─── Tool definitions ──────────────────────────────────────────────


VALID_LOOP_MODES = ["loop", "play once", "single frame"]


SET_GRAPHIC_FIRST_FRAME_TOOL = types.Tool(
    name="set_graphic_first_frame",
    description=(
        "Pin the first element on (layer_name, frame) to a specific "
        "frame of its underlying Graphic Symbol. Used for the "
        "rotation-strip rigging primitive: a limb's Graphic Symbol "
        "has 8-12 drawings at different rotations, and this tool "
        "selects which one shows. loop_mode='single frame' (the "
        "default) freezes the symbol on the chosen frame. Wall time "
        "~17s. No-ops silently if the element is not a Graphic "
        "Symbol instance."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "layer_name": {"type": "string"},
            "frame": {"type": "integer", "minimum": 1, "default": 1},
            "target_first_frame": {
                "type": "integer",
                "minimum": 0,
                "description": "0-indexed frame within the Graphic Symbol's timeline.",
            },
            "loop_mode": {
                "type": "string",
                "enum": VALID_LOOP_MODES,
                "default": "single frame",
            },
        },
        "required": ["fla_path", "layer_name", "target_first_frame"],
        "additionalProperties": False,
    },
)


GET_GRAPHIC_FIRST_FRAME_TOOL = types.Tool(
    name="get_graphic_first_frame",
    description=(
        "READ-only: return the firstFrame, loop, and instanceType "
        "of the first element on (layer_name, frame). Response "
        "shape: {status, found, firstFrame, loop, instanceType, "
        "elapsed_seconds}. firstFrame is null if the element is not "
        "a Graphic Symbol (e.g., a Bitmap or Movie Clip)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "layer_name": {"type": "string"},
            "frame": {"type": "integer", "minimum": 1, "default": 1},
        },
        "required": ["fla_path", "layer_name"],
        "additionalProperties": False,
    },
)


VALIDATE_RIG_TOOL = types.Tool(
    name="validate_rig",
    description=(
        "Validate that the .fla at fla_path conforms to RIG_SPEC_v1 "
        "for the named character identity. Returns a JSON report "
        "with per-rule pass/fail flags and structured error "
        "messages. Used by the orchestrator (Phase 3l) to gate rig "
        "ingestion. Phase 3f v1 checks: root MovieClip name, "
        "required top-level layers, mouth/eye/eyebrow/face switch "
        "states, rotation strip frame counts, _metadata JSON shape. "
        "Defers armature-bone validation to a future fixup."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "identity": {
                "type": "string",
                "description": "Character identity (e.g., 'JETHALAL'). The rig's library must contain a MovieClip named '<IDENTITY>_RIG'.",
            },
        },
        "required": ["fla_path", "identity"],
        "additionalProperties": False,
    },
)


ALL_TOOLS: list[types.Tool] = [
    SET_GRAPHIC_FIRST_FRAME_TOOL,
    GET_GRAPHIC_FIRST_FRAME_TOOL,
    VALIDATE_RIG_TOOL,
]


# ─── Handlers ───────────────────────────────────────────────────────


async def handle_set_graphic_first_frame(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    layer_name = str(args["layer_name"])
    frame = int(args.get("frame", 1))
    target_first_frame = int(args["target_first_frame"])
    loop_mode = str(args.get("loop_mode", "single frame"))

    if loop_mode not in VALID_LOOP_MODES:
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": f"loop_mode must be one of {VALID_LOOP_MODES}; got {loop_mode!r}",
            }),
        )]

    err = _check_fla_exists(fla_path)
    if err:
        return err

    sentinel = _new_sentinel(fla_path)
    _safe_unlink(sentinel)

    template = JSFL_TEMPLATES_DIR / "set_graphic_first_frame.jsfl"
    result = jsfl_bridge.run_jsfl_template(
        template,
        substitutions={
            "FLA_PATH": _to_jsfl_path(fla_path),
            "SENTINEL_PATH": _to_jsfl_path(sentinel),
            "LAYER_NAME": layer_name,
            "FRAME": frame,
            "TARGET_FIRST_FRAME": target_first_frame,
            "LOOP_MODE": loop_mode,
        },
        expected_outputs=[sentinel],
        poll_timeout=180.0,
    )
    _safe_unlink(sentinel)

    if not result.completed_normally:
        return [types.TextContent(
            type="text",
            text=_err(result, fla_path,
                      f"set_graphic_first_frame failed on layer={layer_name!r}"),
        )]
    return [types.TextContent(
        type="text",
        text=_ok(result, fla_path, {
            "layer_name": layer_name,
            "frame": frame,
            "target_first_frame": target_first_frame,
            "loop_mode": loop_mode,
        }),
    )]


async def handle_get_graphic_first_frame(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    layer_name = str(args["layer_name"])
    frame = int(args.get("frame", 1))

    err = _check_fla_exists(fla_path)
    if err:
        return err

    out_json = fla_path.with_suffix(fla_path.suffix + ".graphic.json")
    sentinel = _new_sentinel(out_json)
    _safe_unlink(out_json)
    _safe_unlink(sentinel)

    template = JSFL_TEMPLATES_DIR / "get_graphic_first_frame.jsfl"
    result = jsfl_bridge.run_jsfl_template(
        template,
        substitutions={
            "FLA_PATH": _to_jsfl_path(fla_path),
            "SENTINEL_PATH": _to_jsfl_path(sentinel),
            "LAYER_NAME": layer_name,
            "FRAME": frame,
            "OUT_JSON_PATH": _to_jsfl_path(out_json),
        },
        expected_outputs=[out_json, sentinel],
        poll_timeout=180.0,
    )
    _safe_unlink(sentinel)

    if not result.completed_normally or not out_json.exists():
        _safe_unlink(out_json)
        return [types.TextContent(
            type="text",
            text=_err(result, fla_path,
                      f"get_graphic_first_frame failed on layer={layer_name!r}"),
        )]

    try:
        readback = json.loads(out_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _safe_unlink(out_json)
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": f"get_graphic_first_frame wrote invalid JSON: {exc}",
                "fla_path": str(fla_path),
            }),
        )]
    _safe_unlink(out_json)

    return [types.TextContent(
        type="text",
        text=_ok(result, fla_path, {
            "layer_name": layer_name,
            "frame": frame,
            "found": readback.get("found", False),
            "firstFrame": readback.get("firstFrame"),
            "loop": readback.get("loop"),
            "instanceType": readback.get("instanceType"),
        }),
    )]


async def handle_validate_rig(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    identity = str(args["identity"])

    err = _check_fla_exists(fla_path)
    if err:
        return err

    out_json = fla_path.with_suffix(fla_path.suffix + ".structure.json")
    sentinel = _new_sentinel(out_json)
    _safe_unlink(out_json)
    _safe_unlink(sentinel)

    template = JSFL_TEMPLATES_DIR / "dump_rig_structure.jsfl"
    result = jsfl_bridge.run_jsfl_template(
        template,
        substitutions={
            "FLA_PATH": _to_jsfl_path(fla_path),
            "SENTINEL_PATH": _to_jsfl_path(sentinel),
            "OUT_JSON_PATH": _to_jsfl_path(out_json),
        },
        expected_outputs=[out_json, sentinel],
        poll_timeout=240.0,  # rig dumps can be slower than simple ops
    )
    _safe_unlink(sentinel)

    if not result.completed_normally or not out_json.exists():
        _safe_unlink(out_json)
        return [types.TextContent(
            type="text",
            text=_err(result, fla_path,
                      f"validate_rig: dump_rig_structure JSFL did not complete"),
        )]

    try:
        report = rig_validator.validate_rig_from_json_file(out_json, str(fla_path), identity)
    except Exception as exc:
        _safe_unlink(out_json)
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": f"rig_validator raised: {type(exc).__name__}: {exc}",
                "fla_path": str(fla_path),
            }),
        )]
    _safe_unlink(out_json)

    payload = {
        "status": "ok" if report.passed else "validation_failed",
        "elapsed_seconds": round(result.elapsed_seconds, 2),
        **report.to_dict(),
    }
    return [types.TextContent(type="text", text=json.dumps(payload))]


TOOL_HANDLERS = {
    "set_graphic_first_frame": handle_set_graphic_first_frame,
    "get_graphic_first_frame": handle_get_graphic_first_frame,
    "validate_rig": handle_validate_rig,
}
