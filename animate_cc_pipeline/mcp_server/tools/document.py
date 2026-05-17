"""Document-level MCP tools for Animate CC.

Phase 3c: 5 tools covering the operations needed to set up a fresh
``.fla`` with media references. Each tool is **stateless** — it
opens an `.fla`, performs ONE operation, saves, and closes. Animate
launches and is force-killed per call (~20-25s per call). This is
slow but mechanically clean and matches the bridge's
sentinel-polling + force-kill design.

Long-running Animate-instance reuse (where many JSFL ops share a
single Animate boot) is deferred to Phase 3i. For Phase 3c we
prioritize correctness + composability over throughput.

Tools:
  - ``create_document``      — new .fla at given path
  - ``save_document``        — open existing .fla, save, close (no-op
                               integrity round-trip)
  - ``close_document``       — force-kill any running Animate.exe
  - ``import_image_as_layer``— add layer with imported PNG/JPG
  - ``import_video_as_layer``— add layer with embedded MP4 (animatic
                               reference, background video)
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import mcp.types as types

from .. import jsfl_bridge


# ─── Paths ──────────────────────────────────────────────────────────

JSFL_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "jsfl_templates"


# ─── Helpers ────────────────────────────────────────────────────────


def _to_jsfl_path(p: str | Path) -> str:
    """Normalize a filesystem path for use inside a JSFL substitution.

    Converts backslashes to forward slashes; the JSFL bridge handles
    the rest (URI conversion via ``FLfile.platformPathToURI``).
    """
    return str(p).replace("\\", "/")


def _ok(result: jsfl_bridge.JsflResult, fla_path: Path, extra: dict | None = None) -> str:
    """Build the success JSON for a tool's TextContent response."""
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


def _new_sentinel(near: Path) -> Path:
    """Allocate a sentinel path next to ``near`` (without creating it)."""
    return near.with_suffix(near.suffix + ".sentinel")


# ─── Tool definitions (MCP catalog) ─────────────────────────────────

CREATE_DOCUMENT_TOOL = types.Tool(
    name="create_document",
    description=(
        "Create a new empty Animate CC document (.fla) at the given "
        "path, with the given canvas dimensions and frame rate. "
        "Animate.exe launches, creates the document, saves it, then "
        "is force-killed. Wall time ~20-25s per call. Returns JSON "
        "{status, fla_path, elapsed_seconds, completed_normally}."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {
                "type": "string",
                "description": "Absolute path where the new .fla should be saved.",
            },
            "width": {"type": "integer", "minimum": 16, "default": 1920},
            "height": {"type": "integer", "minimum": 16, "default": 1080},
            "fps": {"type": "integer", "minimum": 1, "maximum": 120, "default": 25},
        },
        "required": ["fla_path"],
        "additionalProperties": False,
    },
)


SAVE_DOCUMENT_TOOL = types.Tool(
    name="save_document",
    description=(
        "Open an existing .fla, save it, close it. Acts as an "
        "integrity round-trip: confirms the file is readable and "
        "writable by Animate, with no other side effects. Useful "
        "after a sequence of import tools to flush any pending "
        "state. Wall time ~20-25s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
        },
        "required": ["fla_path"],
        "additionalProperties": False,
    },
)


CLOSE_DOCUMENT_TOOL = types.Tool(
    name="close_document",
    description=(
        "Force-kill any running Animate.exe process. Stateless "
        "cleanup utility — call this after a hung tool to recover. "
        "Does NOT spawn Animate. Returns JSON {status, killed: bool}."
    ),
    inputSchema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
)


IMPORT_IMAGE_AS_LAYER_TOOL = types.Tool(
    name="import_image_as_layer",
    description=(
        "Open the .fla, add a new layer named layer_name at the top "
        "of the timeline, import a PNG or JPG image onto frame "
        "`frame` of that layer (positioned at the stage center), "
        "save and close. Used for background plates. Wall time "
        "~20-25s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "image_path": {"type": "string"},
            "layer_name": {"type": "string", "default": "BG"},
            "frame": {"type": "integer", "minimum": 1, "default": 1},
        },
        "required": ["fla_path", "image_path"],
        "additionalProperties": False,
    },
)


IMPORT_VIDEO_AS_LAYER_TOOL = types.Tool(
    name="import_video_as_layer",
    description=(
        "Open the .fla, add a new layer named layer_name, import an "
        "MP4 as embedded video onto frame `frame` of that layer, "
        "save and close. Used for animatic-reference layers. Note: "
        "very long MP4s may exceed Animate's embedded-video limit "
        "(~16k frames); for production keep clips under ~10 minutes. "
        "Wall time ~20-30s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "mp4_path": {"type": "string"},
            "layer_name": {"type": "string", "default": "REF_ANIMATIC"},
            "frame": {"type": "integer", "minimum": 1, "default": 1},
        },
        "required": ["fla_path", "mp4_path"],
        "additionalProperties": False,
    },
)


IMPORT_CHARACTER_RIG_TOOL = types.Tool(
    name="import_character_rig",
    description=(
        "Open the target .fla, import a rig .fla into its library "
        "(library-only, no stage placement), add a new top-level "
        "layer named layer_name, and place an instance of the "
        "identity MovieClip symbol on frame `frame` at position "
        "(x, y). Per RIG_SPEC_v1, the rig .fla must contain a "
        "MovieClip with name exactly matching `identity` at library "
        "root. Used by the orchestrator for each character in a "
        "shot. Wall time ~25-35s (rig imports are heavier than "
        "single-asset imports because the whole rig library lands "
        "in the target doc). Returns "
        "{status, fla_path, identity, layer_name, instance_placed}."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "rig_fla_path": {"type": "string"},
            "identity": {
                "type": "string",
                "description": (
                    "Symbol name in the rig library to place "
                    "(e.g. 'JETHALAL'). Per RIG_SPEC_v1."
                ),
            },
            "layer_name": {
                "type": "string",
                "description": (
                    "Layer name to add to target timeline. "
                    "Defaults to identity if not supplied."
                ),
            },
            "frame": {"type": "integer", "minimum": 1, "default": 1},
            "x": {"type": "number", "default": 960},
            "y": {"type": "number", "default": 540},
        },
        "required": ["fla_path", "rig_fla_path", "identity"],
        "additionalProperties": False,
    },
)


ALL_TOOLS: list[types.Tool] = [
    CREATE_DOCUMENT_TOOL,
    SAVE_DOCUMENT_TOOL,
    CLOSE_DOCUMENT_TOOL,
    IMPORT_IMAGE_AS_LAYER_TOOL,
    IMPORT_VIDEO_AS_LAYER_TOOL,
    IMPORT_CHARACTER_RIG_TOOL,
]


# ─── Tool handlers ──────────────────────────────────────────────────


async def handle_create_document(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    width = int(args.get("width", 1920))
    height = int(args.get("height", 1080))
    fps = int(args.get("fps", 25))

    fla_path.parent.mkdir(parents=True, exist_ok=True)
    if fla_path.exists():
        fla_path.unlink()

    sentinel = _new_sentinel(fla_path)
    if sentinel.exists():
        sentinel.unlink()

    template = JSFL_TEMPLATES_DIR / "create_doc.jsfl"
    result = jsfl_bridge.run_jsfl_template(
        template,
        substitutions={
            "FLA_PATH": _to_jsfl_path(fla_path),
            "SENTINEL_PATH": _to_jsfl_path(sentinel),
            "WIDTH": width,
            "HEIGHT": height,
            "FPS": fps,
        },
        expected_outputs=[fla_path, sentinel],
        poll_timeout=180.0,
    )
    _safe_unlink(sentinel)

    if not result.completed_normally or not fla_path.exists():
        return [types.TextContent(
            type="text",
            text=_err(result, fla_path, "create_document did not produce the expected .fla"),
        )]
    return [types.TextContent(
        type="text",
        text=_ok(result, fla_path, {"width": width, "height": height, "fps": fps}),
    )]


async def handle_save_document(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])

    if not fla_path.exists():
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": f"fla_path does not exist: {fla_path}",
                "fla_path": str(fla_path),
            }),
        )]

    sentinel = _new_sentinel(fla_path)
    _safe_unlink(sentinel)

    template = JSFL_TEMPLATES_DIR / "save_doc.jsfl"
    result = jsfl_bridge.run_jsfl_template(
        template,
        substitutions={
            "FLA_PATH": _to_jsfl_path(fla_path),
            "SENTINEL_PATH": _to_jsfl_path(sentinel),
        },
        expected_outputs=[sentinel],
        poll_timeout=180.0,
    )
    _safe_unlink(sentinel)

    if not result.completed_normally:
        return [types.TextContent(
            type="text",
            text=_err(result, fla_path, "save_document did not complete"),
        )]
    return [types.TextContent(type="text", text=_ok(result, fla_path))]


async def handle_close_document(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Force-kill any running Animate.exe. Does not spawn Animate."""
    was_running = jsfl_bridge._animate_running()
    if was_running:
        jsfl_bridge._kill_animate()
    return [types.TextContent(
        type="text",
        text=json.dumps({
            "status": "ok",
            "killed": was_running,
        }),
    )]


async def handle_import_image_as_layer(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    image_path = Path(args["image_path"])
    layer_name = str(args.get("layer_name", "BG"))
    frame = int(args.get("frame", 1))

    for p, name in [(fla_path, "fla_path"), (image_path, "image_path")]:
        if not p.exists():
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error": f"{name} does not exist: {p}",
                }),
            )]

    sentinel = _new_sentinel(fla_path)
    _safe_unlink(sentinel)

    template = JSFL_TEMPLATES_DIR / "import_image.jsfl"
    result = jsfl_bridge.run_jsfl_template(
        template,
        substitutions={
            "FLA_PATH": _to_jsfl_path(fla_path),
            "IMAGE_PATH": _to_jsfl_path(image_path),
            "LAYER_NAME": layer_name,
            "FRAME": frame,
            "SENTINEL_PATH": _to_jsfl_path(sentinel),
        },
        expected_outputs=[sentinel],
        poll_timeout=180.0,
    )
    _safe_unlink(sentinel)

    if not result.completed_normally:
        return [types.TextContent(
            type="text",
            text=_err(result, fla_path, f"import_image_as_layer failed for {image_path}"),
        )]
    return [types.TextContent(
        type="text",
        text=_ok(result, fla_path, {"layer_name": layer_name, "frame": frame}),
    )]


async def handle_import_video_as_layer(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    mp4_path = Path(args["mp4_path"])
    layer_name = str(args.get("layer_name", "REF_ANIMATIC"))
    frame = int(args.get("frame", 1))

    for p, name in [(fla_path, "fla_path"), (mp4_path, "mp4_path")]:
        if not p.exists():
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error": f"{name} does not exist: {p}",
                }),
            )]

    sentinel = _new_sentinel(fla_path)
    _safe_unlink(sentinel)

    template = JSFL_TEMPLATES_DIR / "import_video.jsfl"
    result = jsfl_bridge.run_jsfl_template(
        template,
        substitutions={
            "FLA_PATH": _to_jsfl_path(fla_path),
            "MP4_PATH": _to_jsfl_path(mp4_path),
            "LAYER_NAME": layer_name,
            "FRAME": frame,
            "SENTINEL_PATH": _to_jsfl_path(sentinel),
        },
        expected_outputs=[sentinel],
        poll_timeout=240.0,  # video import can be slower than image
    )
    _safe_unlink(sentinel)

    if not result.completed_normally:
        return [types.TextContent(
            type="text",
            text=_err(result, fla_path, f"import_video_as_layer failed for {mp4_path}"),
        )]
    return [types.TextContent(
        type="text",
        text=_ok(result, fla_path, {"layer_name": layer_name, "frame": frame}),
    )]


async def handle_import_character_rig(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Phase 3o-code: import a rig .fla and place an instance.

    The handler is preflight-only on the Python side: we check both
    target .fla and rig .fla exist, then hand off to JSFL. The JSFL
    writes a sentinel containing either "done", "import_failed", or
    "instance_not_placed" so we can distinguish failure modes.
    """
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    rig_fla_path = Path(args["rig_fla_path"])
    identity = str(args["identity"])
    layer_name = str(args.get("layer_name") or identity)
    frame = int(args.get("frame", 1))
    x = float(args.get("x", 960))
    y = float(args.get("y", 540))

    for p, name in [(fla_path, "fla_path"), (rig_fla_path, "rig_fla_path")]:
        if not p.exists():
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error": f"{name} does not exist: {p}",
                }),
            )]

    sentinel = _new_sentinel(fla_path)
    _safe_unlink(sentinel)

    template = JSFL_TEMPLATES_DIR / "import_character_rig.jsfl"
    result = jsfl_bridge.run_jsfl_template(
        template,
        substitutions={
            "FLA_PATH": _to_jsfl_path(fla_path),
            "RIG_FLA_PATH": _to_jsfl_path(rig_fla_path),
            "IDENTITY": identity,
            "LAYER_NAME": layer_name,
            "FRAME": frame,
            "X": x,
            "Y": y,
            "SENTINEL_PATH": _to_jsfl_path(sentinel),
        },
        expected_outputs=[sentinel],
        poll_timeout=300.0,  # rig imports are heavier (whole library)
    )

    # Read the sentinel content BEFORE unlinking — JSFL writes one
    # of "done", "import_failed", "instance_not_placed".
    sentinel_payload = ""
    try:
        sentinel_payload = sentinel.read_text(encoding="utf-8").strip()
    except (OSError, FileNotFoundError):
        pass
    _safe_unlink(sentinel)

    if not result.completed_normally:
        return [types.TextContent(
            type="text",
            text=_err(result, fla_path,
                      f"import_character_rig did not complete for {rig_fla_path}"),
        )]

    if sentinel_payload == "import_failed":
        return [types.TextContent(
            type="text",
            text=_err(result, fla_path,
                      f"JSFL importFile returned false for rig {rig_fla_path}"),
        )]

    instance_placed = sentinel_payload == "done"
    payload_extra = {
        "identity": identity,
        "layer_name": layer_name,
        "frame": frame,
        "instance_placed": instance_placed,
    }
    if not instance_placed:
        payload_extra["warning"] = (
            f"library imported but instance of {identity!r} "
            "was not placed on stage (symbol not found in rig library?)"
        )
    return [types.TextContent(
        type="text",
        text=_ok(result, fla_path, payload_extra),
    )]


TOOL_HANDLERS = {
    "create_document": handle_create_document,
    "save_document": handle_save_document,
    "close_document": handle_close_document,
    "import_image_as_layer": handle_import_image_as_layer,
    "import_video_as_layer": handle_import_video_as_layer,
    "import_character_rig": handle_import_character_rig,
}


def _safe_unlink(p: Path) -> None:
    try:
        p.unlink()
    except (OSError, FileNotFoundError):
        pass
