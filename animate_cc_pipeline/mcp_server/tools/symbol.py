"""Symbol placement and instance-manipulation MCP tools.

Phase 3d: 4 tools covering the operations that put symbols on the
stage and tweak their transform properties across frames. Combined
with Phase 3c's import tools, this is enough to lay out a frame:
import a symbol → place an instance → set position/scale/rotation
to match the rough animatic's bbox.

**Identification model**: each modify tool finds its target by
**layer name + frame number** (1-indexed externally, 0-indexed in
JSFL). The first element on that (layer, frame) is the target. This
matches the rigging workflow — one rigged character per layer per
shot.

Each tool launches Animate, does ONE operation, saves, closes,
force-kills. Long-running instance reuse remains deferred to Phase
3i.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import mcp.types as types

from .. import jsfl_bridge


JSFL_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "jsfl_templates"


# ─── Shared helpers (mirrored from document.py) ─────────────────────


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


# ─── Tool definitions (MCP catalog) ─────────────────────────────────

PLACE_SYMBOL_INSTANCE_TOOL = types.Tool(
    name="place_symbol_instance",
    description=(
        "Place an instance of an existing library symbol onto a "
        "layer at the given frame and stage coordinates (x, y). The "
        "layer is auto-created if it does not exist. The symbol "
        "must already be present in the .fla's Library (e.g. via "
        "import_image_as_layer or import_character_rig in a future "
        "phase). Wall time ~20s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "symbol_name": {
                "type": "string",
                "description": "Name of the library item to instance (e.g. 'JETHALAL_RIG').",
            },
            "layer_name": {"type": "string"},
            "frame": {"type": "integer", "minimum": 1, "default": 1},
            "x": {"type": "number", "default": 0},
            "y": {"type": "number", "default": 0},
        },
        "required": ["fla_path", "symbol_name", "layer_name"],
        "additionalProperties": False,
    },
)


SET_INSTANCE_POSITION_TOOL = types.Tool(
    name="set_instance_position",
    description=(
        "Set the (x, y) stage position of the first element on "
        "layer_name at the given frame. The frame is 1-indexed. "
        "If no element is found on that layer+frame, returns an "
        "error. Wall time ~17s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "layer_name": {"type": "string"},
            "frame": {"type": "integer", "minimum": 1, "default": 1},
            "x": {"type": "number"},
            "y": {"type": "number"},
        },
        "required": ["fla_path", "layer_name", "x", "y"],
        "additionalProperties": False,
    },
)


SET_INSTANCE_SCALE_TOOL = types.Tool(
    name="set_instance_scale",
    description=(
        "Set the scaleX / scaleY of the first element on "
        "layer_name at the given frame. Use values like 0.5 (half) "
        "or 2.0 (double). Wall time ~17s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "layer_name": {"type": "string"},
            "frame": {"type": "integer", "minimum": 1, "default": 1},
            "sx": {"type": "number"},
            "sy": {"type": "number"},
        },
        "required": ["fla_path", "layer_name", "sx", "sy"],
        "additionalProperties": False,
    },
)


SET_INSTANCE_ROTATION_TOOL = types.Tool(
    name="set_instance_rotation",
    description=(
        "Set the rotation (degrees, clockwise positive) of the "
        "first element on layer_name at the given frame. Wall time "
        "~17s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "layer_name": {"type": "string"},
            "frame": {"type": "integer", "minimum": 1, "default": 1},
            "angle": {"type": "number"},
        },
        "required": ["fla_path", "layer_name", "angle"],
        "additionalProperties": False,
    },
)


ALL_TOOLS: list[types.Tool] = [
    PLACE_SYMBOL_INSTANCE_TOOL,
    SET_INSTANCE_POSITION_TOOL,
    SET_INSTANCE_SCALE_TOOL,
    SET_INSTANCE_ROTATION_TOOL,
]


# ─── Common pre-check shared by all 4 handlers ──────────────────────


def _check_fla_exists(fla_path: Path) -> list[types.TextContent] | None:
    """Return a TextContent error list if fla_path is missing, else None."""
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


def _run(
    template_name: str,
    substitutions: dict[str, Any],
    fla_path: Path,
    poll_timeout: float = 180.0,
    success_extra: dict | None = None,
    failure_message: str = "operation failed",
) -> list[types.TextContent]:
    """Common dispatch: render the named template, poll for sentinel,
    return ok/err TextContent.
    """
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


# ─── Handlers ───────────────────────────────────────────────────────


async def handle_place_symbol_instance(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    symbol_name = str(args["symbol_name"])
    layer_name = str(args["layer_name"])
    frame = int(args.get("frame", 1))
    x = float(args.get("x", 0))
    y = float(args.get("y", 0))

    err = _check_fla_exists(fla_path)
    if err:
        return err

    return _run(
        "place_symbol_instance.jsfl",
        {
            "SYMBOL_NAME": symbol_name,
            "LAYER_NAME": layer_name,
            "FRAME": frame,
            "X": x,
            "Y": y,
        },
        fla_path,
        success_extra={
            "symbol_name": symbol_name,
            "layer_name": layer_name,
            "frame": frame,
            "x": x,
            "y": y,
        },
        failure_message=f"place_symbol_instance failed for symbol={symbol_name!r}",
    )


async def handle_set_instance_position(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    layer_name = str(args["layer_name"])
    frame = int(args.get("frame", 1))
    x = float(args["x"])
    y = float(args["y"])

    err = _check_fla_exists(fla_path)
    if err:
        return err

    return _run(
        "set_instance_position.jsfl",
        {"LAYER_NAME": layer_name, "FRAME": frame, "X": x, "Y": y},
        fla_path,
        success_extra={"layer_name": layer_name, "frame": frame, "x": x, "y": y},
        failure_message=f"set_instance_position failed on layer={layer_name!r} frame={frame}",
    )


async def handle_set_instance_scale(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    layer_name = str(args["layer_name"])
    frame = int(args.get("frame", 1))
    sx = float(args["sx"])
    sy = float(args["sy"])

    err = _check_fla_exists(fla_path)
    if err:
        return err

    return _run(
        "set_instance_scale.jsfl",
        {"LAYER_NAME": layer_name, "FRAME": frame, "SX": sx, "SY": sy},
        fla_path,
        success_extra={"layer_name": layer_name, "frame": frame, "sx": sx, "sy": sy},
        failure_message=f"set_instance_scale failed on layer={layer_name!r} frame={frame}",
    )


async def handle_set_instance_rotation(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    layer_name = str(args["layer_name"])
    frame = int(args.get("frame", 1))
    angle = float(args["angle"])

    err = _check_fla_exists(fla_path)
    if err:
        return err

    return _run(
        "set_instance_rotation.jsfl",
        {"LAYER_NAME": layer_name, "FRAME": frame, "ANGLE": angle},
        fla_path,
        success_extra={"layer_name": layer_name, "frame": frame, "angle": angle},
        failure_message=f"set_instance_rotation failed on layer={layer_name!r} frame={frame}",
    )


TOOL_HANDLERS = {
    "place_symbol_instance": handle_place_symbol_instance,
    "set_instance_position": handle_set_instance_position,
    "set_instance_scale": handle_set_instance_scale,
    "set_instance_rotation": handle_set_instance_rotation,
}
