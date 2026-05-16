"""Tween MCP tools.

Phase 3g: 3 MCP tools for adding tweens between keyframes and
controlling their easing curve. Useful for sparse-keyframing
workflows where the orchestrator places keyframes at major poses
and lets Animate interpolate the in-between frames smoothly.

For the rigging workflow's per-frame-keyframing pattern (the
orchestrator's primary mode), tweens are unnecessary — every frame
is a keyframe and the result is a stepped sequence. Tweens become
useful when the orchestrator decides to thin out keyframes for
shots with smooth motion.

Tools:
  - add_classic_tween     sets frame.tweenType = "motion"
                          (Animate's "Classic Tween" UI command)
  - add_motion_tween      Timeline.createMotionObject(start, end)
                          (newer Motion Tween span; experimental)
  - set_easing            frame.tweenEasing (-100 to +100)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import mcp.types as types

from .. import jsfl_bridge


JSFL_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "jsfl_templates"


# ─── Shared helpers (mirror other tool modules) ────────────────────


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


def _run_mutating(
    template_name: str,
    substitutions: dict[str, Any],
    fla_path: Path,
    success_extra: dict | None,
    failure_message: str,
    poll_timeout: float = 180.0,
) -> list[types.TextContent]:
    sentinel = _new_sentinel(fla_path)
    _safe_unlink(sentinel)

    full_subs = {
        "FLA_PATH": _to_jsfl_path(fla_path),
        "SENTINEL_PATH": _to_jsfl_path(sentinel),
        **substitutions,
    }

    template = JSFL_TEMPLATES_DIR / template_name
    result = jsfl_bridge.run_jsfl_template(
        template,
        substitutions=full_subs,
        expected_outputs=[sentinel],
        poll_timeout=poll_timeout,
    )
    _safe_unlink(sentinel)

    if not result.completed_normally:
        return [types.TextContent(
            type="text",
            text=_err(result, fla_path, failure_message),
        )]
    return [types.TextContent(
        type="text",
        text=_ok(result, fla_path, success_extra),
    )]


# ─── Tool definitions ───────────────────────────────────────────────


ADD_CLASSIC_TWEEN_TOOL = types.Tool(
    name="add_classic_tween",
    description=(
        "Add a Classic Tween to the keyframe at start_frame on "
        "layer_name. Animate will then interpolate position, "
        "rotation, scale, and color from that keyframe to the next "
        "keyframe on the same layer. Implemented via "
        "`frame.tweenType = \"motion\"`. Both keyframes must exist "
        "and contain a symbol instance (not raw shapes). Wall time "
        "~17s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "layer_name": {"type": "string"},
            "start_frame": {"type": "integer", "minimum": 1},
        },
        "required": ["fla_path", "layer_name", "start_frame"],
        "additionalProperties": False,
    },
)


ADD_MOTION_TWEEN_TOOL = types.Tool(
    name="add_motion_tween",
    description=(
        "Create a modern Motion Tween span between start_frame and "
        "end_frame on layer_name via "
        "`Timeline.createMotionObject(start, end)`. EXPERIMENTAL on "
        "Animate 2020 — newer JSFL APIs have shown gotchas (see "
        "remove_keyframe / convertToFrames). If this hangs or "
        "errors, fall back to add_classic_tween. Wall time ~17-25s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "layer_name": {"type": "string"},
            "start_frame": {"type": "integer", "minimum": 1},
            "end_frame": {"type": "integer", "minimum": 1},
        },
        "required": ["fla_path", "layer_name", "start_frame", "end_frame"],
        "additionalProperties": False,
    },
)


SET_EASING_TOOL = types.Tool(
    name="set_easing",
    description=(
        "Set the easing curve on the starting keyframe of a tween. "
        "`frame.tweenEasing` is an integer in [-100, 100]: 0 = "
        "linear (constant velocity), -100 = pure ease-in (slow "
        "start), +100 = pure ease-out (slow end). Intermediate "
        "values blend. Sets via `frame.tweenEasing = N` on the "
        "keyframe at `frame` of `layer_name`. Wall time ~17s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "layer_name": {"type": "string"},
            "frame": {"type": "integer", "minimum": 1},
            "easing": {
                "type": "integer",
                "minimum": -100,
                "maximum": 100,
                "description": "Easing curve: -100=ease-in, 0=linear, +100=ease-out",
            },
        },
        "required": ["fla_path", "layer_name", "frame", "easing"],
        "additionalProperties": False,
    },
)


ALL_TOOLS: list[types.Tool] = [
    ADD_CLASSIC_TWEEN_TOOL,
    ADD_MOTION_TWEEN_TOOL,
    SET_EASING_TOOL,
]


# ─── Handlers ───────────────────────────────────────────────────────


async def handle_add_classic_tween(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    layer_name = str(args["layer_name"])
    start_frame = int(args["start_frame"])

    err = _check_fla_exists(fla_path)
    if err:
        return err

    return _run_mutating(
        "add_classic_tween.jsfl",
        {"LAYER_NAME": layer_name, "START_FRAME": start_frame},
        fla_path,
        success_extra={"layer_name": layer_name, "start_frame": start_frame},
        failure_message=f"add_classic_tween failed on layer={layer_name!r} frame={start_frame}",
    )


async def handle_add_motion_tween(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    layer_name = str(args["layer_name"])
    start_frame = int(args["start_frame"])
    end_frame = int(args["end_frame"])

    if end_frame <= start_frame:
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": f"end_frame ({end_frame}) must be > start_frame ({start_frame})",
            }),
        )]

    err = _check_fla_exists(fla_path)
    if err:
        return err

    return _run_mutating(
        "add_motion_tween.jsfl",
        {
            "LAYER_NAME": layer_name,
            "START_FRAME": start_frame,
            "END_FRAME": end_frame,
        },
        fla_path,
        success_extra={
            "layer_name": layer_name,
            "start_frame": start_frame,
            "end_frame": end_frame,
        },
        failure_message=(
            f"add_motion_tween failed on layer={layer_name!r} "
            f"frames {start_frame}..{end_frame}"
        ),
        poll_timeout=240.0,  # extra grace for the newer API
    )


async def handle_set_easing(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    layer_name = str(args["layer_name"])
    frame = int(args["frame"])
    easing = int(args["easing"])

    if not (-100 <= easing <= 100):
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": f"easing must be in [-100, 100]; got {easing}",
            }),
        )]

    err = _check_fla_exists(fla_path)
    if err:
        return err

    return _run_mutating(
        "set_easing.jsfl",
        {"LAYER_NAME": layer_name, "FRAME": frame, "EASING": easing},
        fla_path,
        success_extra={"layer_name": layer_name, "frame": frame, "easing": easing},
        failure_message=f"set_easing failed on layer={layer_name!r} frame={frame}",
    )


TOOL_HANDLERS = {
    "add_classic_tween": handle_add_classic_tween,
    "add_motion_tween": handle_add_motion_tween,
    "set_easing": handle_set_easing,
}
