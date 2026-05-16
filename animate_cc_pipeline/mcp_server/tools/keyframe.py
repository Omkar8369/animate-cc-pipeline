"""Keyframe MCP tools.

Phase 3e: 4 tools covering keyframe insertion, deletion, and
read-back. Combined with Phase 3d's transform tools, this is enough
for the orchestrator (Phase 3l) to keyframe per-frame transforms
along the timeline of a shot.

Tools:
  - ``insert_keyframe``       inserts a keyframe (content inherited
                              from the preceding keyframe)
  - ``insert_blank_keyframe`` inserts a blank keyframe
  - ``remove_keyframe``       clears keyframe status of a frame
  - ``get_keyframes``         READ-only: returns the list of frame
                              indices that have keyframes on a layer

Each modify tool is stateless (open .fla, mutate, save, close,
force-kill Animate). ``get_keyframes`` writes a JSON result file
that the Python handler reads + returns inline in the
TextContent response.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import mcp.types as types

from .. import jsfl_bridge


JSFL_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "jsfl_templates"


# ─── Shared helpers ────────────────────────────────────────────────


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
    """Common 'mutate the .fla + sentinel' dispatch shared by the
    three write tools."""
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

INSERT_KEYFRAME_TOOL = types.Tool(
    name="insert_keyframe",
    description=(
        "Insert a keyframe on layer_name at the given 1-indexed "
        "frame. The new keyframe inherits content from the "
        "preceding keyframe (so any symbol instance carries over "
        "and can then be tweaked via set_instance_*). If the frame "
        "is past the layer's current end, the layer extends. Wall "
        "time ~17s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "layer_name": {"type": "string"},
            "frame": {"type": "integer", "minimum": 1},
        },
        "required": ["fla_path", "layer_name", "frame"],
        "additionalProperties": False,
    },
)


INSERT_BLANK_KEYFRAME_TOOL = types.Tool(
    name="insert_blank_keyframe",
    description=(
        "Insert a BLANK keyframe on layer_name at the given "
        "1-indexed frame. Unlike insert_keyframe, the new keyframe "
        "starts with NO content — useful when the next pose should "
        "be drawn from scratch rather than tweaked from the prior "
        "keyframe. Wall time ~17s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "layer_name": {"type": "string"},
            "frame": {"type": "integer", "minimum": 1},
        },
        "required": ["fla_path", "layer_name", "frame"],
        "additionalProperties": False,
    },
)


REMOVE_KEYFRAME_TOOL = types.Tool(
    name="remove_keyframe",
    description=(
        "Remove keyframe status from frame on layer_name. The frame "
        "slot is preserved but now extends content from the prior "
        "keyframe instead of starting its own. Wall time ~17s. "
        "KNOWN ISSUE (Animate 2020): `Timeline.clearKeyframes` hangs "
        "JSFL behind what appears to be an undismissable confirmation "
        "dialog. Tool is shipped for forward compatibility (likely "
        "works in Animate 2022+) but the Phase 3e smoke skips its "
        "live verification. Use with caution on Animate 2020 — call "
        "may time out and the bridge will force-kill Animate. The "
        "orchestrator (Phase 3l) plans an insert-heavy pipeline; "
        "rarely needs remove."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "layer_name": {"type": "string"},
            "frame": {"type": "integer", "minimum": 1},
        },
        "required": ["fla_path", "layer_name", "frame"],
        "additionalProperties": False,
    },
)


GET_KEYFRAMES_TOOL = types.Tool(
    name="get_keyframes",
    description=(
        "READ-only tool. Returns a sorted JSON list of 1-indexed "
        "frame numbers on which layer_name has keyframes. Used by "
        "the orchestrator + smoke tests to verify keyframe layout "
        "after write tools. Response shape: "
        "{status, fla_path, layer_name, keyframes: [int, ...], "
        "elapsed_seconds}. Wall time ~17s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "layer_name": {"type": "string"},
        },
        "required": ["fla_path", "layer_name"],
        "additionalProperties": False,
    },
)


ALL_TOOLS: list[types.Tool] = [
    INSERT_KEYFRAME_TOOL,
    INSERT_BLANK_KEYFRAME_TOOL,
    REMOVE_KEYFRAME_TOOL,
    GET_KEYFRAMES_TOOL,
]


# ─── Handlers ───────────────────────────────────────────────────────


async def handle_insert_keyframe(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    layer_name = str(args["layer_name"])
    frame = int(args["frame"])

    err = _check_fla_exists(fla_path)
    if err:
        return err

    return _run_mutating(
        "insert_keyframe.jsfl",
        {"LAYER_NAME": layer_name, "FRAME": frame},
        fla_path,
        success_extra={"layer_name": layer_name, "frame": frame},
        failure_message=f"insert_keyframe failed on layer={layer_name!r} frame={frame}",
    )


async def handle_insert_blank_keyframe(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    layer_name = str(args["layer_name"])
    frame = int(args["frame"])

    err = _check_fla_exists(fla_path)
    if err:
        return err

    return _run_mutating(
        "insert_blank_keyframe.jsfl",
        {"LAYER_NAME": layer_name, "FRAME": frame},
        fla_path,
        success_extra={"layer_name": layer_name, "frame": frame},
        failure_message=f"insert_blank_keyframe failed on layer={layer_name!r} frame={frame}",
    )


async def handle_remove_keyframe(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    layer_name = str(args["layer_name"])
    frame = int(args["frame"])

    err = _check_fla_exists(fla_path)
    if err:
        return err

    return _run_mutating(
        "remove_keyframe.jsfl",
        {"LAYER_NAME": layer_name, "FRAME": frame},
        fla_path,
        success_extra={"layer_name": layer_name, "frame": frame},
        failure_message=f"remove_keyframe failed on layer={layer_name!r} frame={frame}",
    )


async def handle_get_keyframes(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    layer_name = str(args["layer_name"])

    err = _check_fla_exists(fla_path)
    if err:
        return err

    # get_keyframes uses an extra OUT_JSON_PATH the JSFL writes results to.
    # Place it adjacent to the .fla rather than using tempfile.mkstemp
    # (mkstemp returns an open fd; on Windows the open handle keeps the
    # empty file alive even after unlink, which then races with JSFL's
    # FLfile.write and the bridge's expected_outputs check).
    out_json = fla_path.with_suffix(fla_path.suffix + ".keyframes.json")
    sentinel = _new_sentinel(out_json)
    _safe_unlink(out_json)
    _safe_unlink(sentinel)

    template = JSFL_TEMPLATES_DIR / "get_keyframes.jsfl"
    result = jsfl_bridge.run_jsfl_template(
        template,
        substitutions={
            "FLA_PATH": _to_jsfl_path(fla_path),
            "LAYER_NAME": layer_name,
            "OUT_JSON_PATH": _to_jsfl_path(out_json),
            "SENTINEL_PATH": _to_jsfl_path(sentinel),
        },
        expected_outputs=[out_json, sentinel],
        poll_timeout=180.0,
    )
    _safe_unlink(sentinel)

    if not result.completed_normally or not out_json.exists():
        _safe_unlink(out_json)
        return [types.TextContent(
            type="text",
            text=_err(result, fla_path, f"get_keyframes failed for layer={layer_name!r}"),
        )]

    try:
        readback = json.loads(out_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _safe_unlink(out_json)
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": f"get_keyframes wrote invalid JSON: {exc}",
                "fla_path": str(fla_path),
                "layer_name": layer_name,
            }),
        )]
    _safe_unlink(out_json)

    keyframes = sorted(readback.get("keyframes", []))
    layer_found = bool(readback.get("layer_found", False))

    return [types.TextContent(
        type="text",
        text=_ok(result, fla_path, {
            "layer_name": layer_name,
            "layer_found": layer_found,
            "keyframes": keyframes,
        }),
    )]


TOOL_HANDLERS = {
    "insert_keyframe": handle_insert_keyframe,
    "insert_blank_keyframe": handle_insert_blank_keyframe,
    "remove_keyframe": handle_remove_keyframe,
    "get_keyframes": handle_get_keyframes,
}
