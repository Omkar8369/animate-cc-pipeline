"""Camera + render MCP tools.

Phase 3i — final tool phase before orchestrator work. Three tools:
camera positioning + two render variants (full + preview).

Render strategy: two-stage. JSFL exports a PNG sequence to a temp
directory; Python uses imageio-ffmpeg (already in requirements) to
encode the sequence into an MP4 at the specified FPS. This avoids
depending on Animate's native MP4 codec licensing, which varies
between Animate versions and licensing tiers.

Tools:
  - set_camera_position    EXPERIMENTAL — manipulate Animate's
                           Camera layer transform via JSFL.
  - render_to_mp4          render entire timeline → MP4.
  - render_preview         render a frame range → MP4.
"""

from __future__ import annotations

import json
import shutil
import subprocess
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


def _encode_png_sequence_to_mp4(
    png_dir: Path,
    out_path: Path,
    fps: int,
) -> tuple[bool, str, int]:
    """Use imageio-ffmpeg to encode a PNG sequence into MP4.

    Returns (ok, message, frame_count). Cleans up nothing.
    """
    try:
        import imageio_ffmpeg
    except ImportError:
        return False, "imageio-ffmpeg not installed", 0

    pngs = sorted(png_dir.glob("*.png"))
    if not pngs:
        return False, f"no PNG frames found in {png_dir}", 0

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Use the actual first PNG's filename pattern. Animate's export
    # numbers files with a per-frame suffix; we glob to find the
    # pattern.
    first = pngs[0]
    # If filenames look like prefix0001.png, prefix0002.png, etc.,
    # use a glob pattern via ffmpeg's image2 demuxer.
    cmd = [
        ffmpeg, "-y",
        "-framerate", str(fps),
        "-i", str(first.parent / "*.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",  # ensure even dims (libx264 requirement)
        "-pattern_type", "glob",
        str(out_path),
    ]
    # Need to put -pattern_type BEFORE -i for ffmpeg arg order.
    cmd = [
        ffmpeg, "-y",
        "-framerate", str(fps),
        "-pattern_type", "glob",
        "-i", str(first.parent / "*.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        str(out_path),
    ]
    completed = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120
    )
    if completed.returncode != 0 or not out_path.exists():
        # ffmpeg may not support glob on Windows; fall back to explicit
        # numeric pattern detection.
        stem = first.stem
        # Find the numeric suffix length
        import re
        m = re.search(r"(\d+)$", stem)
        if m:
            num_len = len(m.group(1))
            prefix = stem[: -num_len]
            pattern = str(first.parent / f"{prefix}%0{num_len}d.png")
            cmd2 = [
                ffmpeg, "-y",
                "-framerate", str(fps),
                "-start_number", str(int(m.group(1))),
                "-i", pattern,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                str(out_path),
            ]
            completed = subprocess.run(
                cmd2, capture_output=True, text=True, timeout=120
            )

    if completed.returncode != 0 or not out_path.exists():
        return False, (
            f"ffmpeg failed (exit={completed.returncode}): "
            f"{completed.stderr[-400:]}"
        ), len(pngs)
    return True, "ok", len(pngs)


# ─── Tool definitions ──────────────────────────────────────────────


SET_CAMERA_POSITION_TOOL = types.Tool(
    name="set_camera_position",
    description=(
        "EXPERIMENTAL. Set Animate's Camera layer transform at "
        "`frame`. Animate added the Camera in CC 2018; JSFL surface "
        "is sparse so this tool is best-effort. (x, y) is the camera "
        "translation in stage pixels, zoom is a multiplier (1.0 = "
        "100%), rotation is in degrees. Wall time ~17s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "frame": {"type": "integer", "minimum": 1, "default": 1},
            "x": {"type": "number", "default": 0},
            "y": {"type": "number", "default": 0},
            "zoom": {"type": "number", "default": 1.0, "minimum": 0.01},
            "rotation": {"type": "number", "default": 0},
        },
        "required": ["fla_path"],
        "additionalProperties": False,
    },
)


RENDER_TO_MP4_TOOL = types.Tool(
    name="render_to_mp4",
    description=(
        "Render the .fla's full timeline to an MP4 at the given FPS. "
        "Two-stage: JSFL exports a PNG sequence to a temp dir, "
        "Python encodes via imageio-ffmpeg (libx264 + yuv420p). "
        "Returns the output path + frame count. Wall time ~30-60s "
        "depending on timeline length."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "out_path": {"type": "string"},
            "fps": {"type": "integer", "minimum": 1, "maximum": 120, "default": 25},
        },
        "required": ["fla_path", "out_path"],
        "additionalProperties": False,
    },
)


RENDER_PREVIEW_TOOL = types.Tool(
    name="render_preview",
    description=(
        "Render a frame range of the .fla to an MP4 for quick "
        "verification. Same encoding pipeline as render_to_mp4 but "
        "limited to (start_frame, end_frame). Both bounds are "
        "1-indexed and inclusive. Wall time ~20-40s."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "fla_path": {"type": "string"},
            "out_path": {"type": "string"},
            "start_frame": {"type": "integer", "minimum": 1},
            "end_frame": {"type": "integer", "minimum": 1},
            "fps": {"type": "integer", "minimum": 1, "maximum": 120, "default": 25},
        },
        "required": ["fla_path", "out_path", "start_frame", "end_frame"],
        "additionalProperties": False,
    },
)


ALL_TOOLS: list[types.Tool] = [
    SET_CAMERA_POSITION_TOOL,
    RENDER_TO_MP4_TOOL,
    RENDER_PREVIEW_TOOL,
]


# ─── Handlers ──────────────────────────────────────────────────────


async def handle_set_camera_position(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    frame = int(args.get("frame", 1))
    x = float(args.get("x", 0))
    y = float(args.get("y", 0))
    zoom = float(args.get("zoom", 1.0))
    rotation = float(args.get("rotation", 0))

    err = _check_fla_exists(fla_path)
    if err:
        return err

    sentinel = _new_sentinel(fla_path)
    _safe_unlink(sentinel)

    template = JSFL_TEMPLATES_DIR / "set_camera_position.jsfl"
    result = jsfl_bridge.run_jsfl_template(
        template,
        substitutions={
            "FLA_PATH": _to_jsfl_path(fla_path),
            "FRAME": frame,
            "X": x,
            "Y": y,
            "ZOOM": zoom,
            "ROTATION": rotation,
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
                      "set_camera_position did not complete (experimental — may need fixup)"),
        )]
    return [types.TextContent(
        type="text",
        text=_ok(result, fla_path, {
            "frame": frame, "x": x, "y": y, "zoom": zoom, "rotation": rotation,
            "note": "experimental — Camera JSFL surface is sparse on Animate 2020",
        }),
    )]


async def _do_render(
    fla_path: Path,
    out_path: Path,
    start_frame: int | None,
    end_frame: int | None,
    fps: int,
) -> tuple[bool, dict, jsfl_bridge.JsflResult | None]:
    """Common render-to-MP4 dispatch shared by both render tools.

    Returns (success, payload_extra, jsfl_result). jsfl_result is
    None if the failure was on the Python side (no Animate launch).
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _safe_unlink(out_path)

    # Allocate a temp directory for the PNG sequence
    png_dir = Path(tempfile.mkdtemp(prefix="animate_render_"))
    png_prefix = png_dir / "frame_"
    sentinel = png_dir / "render.sentinel"

    try:
        # JSFL prep: path string ending without extension is the
        # prefix Animate uses to number frame_NNNN.png files.
        # Map None → -1 so JSFL knows "no range".
        start_jsfl = -1 if start_frame is None else (start_frame - 1)
        end_jsfl = -1 if end_frame is None else (end_frame - 1)

        template = JSFL_TEMPLATES_DIR / "export_png_sequence.jsfl"
        jsfl_result = jsfl_bridge.run_jsfl_template(
            template,
            substitutions={
                "FLA_PATH": _to_jsfl_path(fla_path),
                "PNG_PREFIX_PATH": _to_jsfl_path(png_prefix),
                "START_FRAME_IDX0": start_jsfl,
                "END_FRAME_IDX0": end_jsfl,
                "SENTINEL_PATH": _to_jsfl_path(sentinel),
            },
            expected_outputs=[sentinel],
            poll_timeout=300.0,
        )

        if not jsfl_result.completed_normally:
            return False, {
                "error": "JSFL PNG-export did not complete",
                "missing_outputs": [str(p) for p in jsfl_result.missing_outputs],
            }, jsfl_result

        # Encode the PNG sequence to MP4
        ok, msg, frame_count = _encode_png_sequence_to_mp4(png_dir, out_path, fps)
        if not ok:
            return False, {
                "error": f"PNG-to-MP4 encode failed: {msg}",
                "png_count": frame_count,
            }, jsfl_result

        if not out_path.exists() or out_path.stat().st_size == 0:
            return False, {
                "error": "encoded MP4 missing or empty",
                "png_count": frame_count,
            }, jsfl_result

        return True, {
            "out_path": str(out_path),
            "out_size_bytes": out_path.stat().st_size,
            "frame_count": frame_count,
            "fps": fps,
        }, jsfl_result
    finally:
        # Always clean up the temp PNG dir
        try:
            shutil.rmtree(png_dir, ignore_errors=True)
        except Exception:
            pass


async def handle_render_to_mp4(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    out_path = Path(args["out_path"])
    fps = int(args.get("fps", 25))

    err = _check_fla_exists(fla_path)
    if err:
        return err

    success, extra, jsfl_result = await _do_render(
        fla_path, out_path, start_frame=None, end_frame=None, fps=fps,
    )

    if not success:
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": extra.get("error", "render failed"),
                "fla_path": str(fla_path),
                **{k: v for k, v in extra.items() if k != "error"},
            }),
        )]

    elapsed = jsfl_result.elapsed_seconds if jsfl_result else 0.0
    return [types.TextContent(
        type="text",
        text=json.dumps({
            "status": "ok",
            "fla_path": str(fla_path),
            "elapsed_seconds": round(elapsed, 2),
            **extra,
        }),
    )]


async def handle_render_preview(arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    fla_path = Path(args["fla_path"])
    out_path = Path(args["out_path"])
    start_frame = int(args["start_frame"])
    end_frame = int(args["end_frame"])
    fps = int(args.get("fps", 25))

    if end_frame < start_frame:
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": f"end_frame ({end_frame}) must be >= start_frame ({start_frame})",
            }),
        )]

    err = _check_fla_exists(fla_path)
    if err:
        return err

    success, extra, jsfl_result = await _do_render(
        fla_path, out_path, start_frame=start_frame, end_frame=end_frame, fps=fps,
    )

    if not success:
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": extra.get("error", "render failed"),
                "fla_path": str(fla_path),
                **{k: v for k, v in extra.items() if k != "error"},
            }),
        )]

    elapsed = jsfl_result.elapsed_seconds if jsfl_result else 0.0
    return [types.TextContent(
        type="text",
        text=json.dumps({
            "status": "ok",
            "fla_path": str(fla_path),
            "elapsed_seconds": round(elapsed, 2),
            "start_frame": start_frame,
            "end_frame": end_frame,
            **extra,
        }),
    )]


TOOL_HANDLERS = {
    "set_camera_position": handle_set_camera_position,
    "render_to_mp4": handle_render_to_mp4,
    "render_preview": handle_render_preview,
}
