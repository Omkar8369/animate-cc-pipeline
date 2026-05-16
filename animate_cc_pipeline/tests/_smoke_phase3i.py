"""End-to-end smoke for Phase 3i camera + render tools.

Run manually:
    <python> animate_cc_pipeline/tests/_smoke_phase3i.py

What this proves:
1. Set up a .fla with content across multiple frames (so the render
   produces a non-trivial video).
2. `render_to_mp4` writes a playable MP4 of the full timeline.
3. `render_preview` writes a shorter MP4 of a frame range.
4. `set_camera_position` attempted at frame 1 — experimental, non-fatal.

Wall time ~150-220s (5-6 Animate launches + PNG-to-MP4 encoding).
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _print(line: str) -> None:
    print(line, flush=True)


def _step(name: str, ok: bool, detail: str = "") -> None:
    icon = "OK  " if ok else "FAIL"
    _print(f"  [{icon}] {name}" + (f" - {detail}" if detail else ""))


def _make_test_png(path: Path) -> None:
    from PIL import Image  # type: ignore

    img = Image.new("RGB", (64, 64), color=(255, 100, 50))
    img.save(path, format="PNG")


def main() -> int:
    _print("=" * 60)
    _print("Phase 3i smoke test")
    _print("=" * 60)

    try:
        from animate_cc_pipeline.mcp_server.tools import document as doc_tools
        from animate_cc_pipeline.mcp_server.tools import keyframe as kf_tools
        from animate_cc_pipeline.mcp_server.tools import symbol as sym_tools
        from animate_cc_pipeline.mcp_server.tools import camera as cam_tools
        from animate_cc_pipeline.mcp_server import jsfl_bridge
    except Exception as exc:
        _step("imports", False, str(exc))
        return 1
    _step("imports", True)

    try:
        animate_exe = jsfl_bridge._resolve_animate_exe()
    except FileNotFoundError as exc:
        _step("resolve Animate.exe", False, str(exc).splitlines()[0])
        return 2
    _step("resolve Animate.exe", True, str(animate_exe))

    with tempfile.TemporaryDirectory(prefix="animate_smoke3i_") as tmp:
        tmp_dir = Path(tmp)
        fla = tmp_dir / "phase3i.fla"
        png = tmp_dir / "tile.png"
        full_mp4 = tmp_dir / "full.mp4"
        preview_mp4 = tmp_dir / "preview.mp4"

        _make_test_png(png)

        # 1. Setup: create + import image (frame 1 has content)
        _print("  ... create_document + import_image_as_layer (2x launches)")
        r = asyncio.run(doc_tools.handle_create_document({
            "fla_path": str(fla), "width": 320, "height": 240, "fps": 25,
        }))
        if json.loads(r[0].text).get("status") != "ok":
            _step("create_document", False, r[0].text); return 3
        r = asyncio.run(doc_tools.handle_import_image_as_layer({
            "fla_path": str(fla), "image_path": str(png),
            "layer_name": "BG", "frame": 1,
        }))
        if json.loads(r[0].text).get("status") != "ok":
            _step("import_image_as_layer", False, r[0].text); return 4
        _step("setup (create + import)", True)

        # 2. Add a second keyframe with motion (so the render shows movement)
        _print("  ... insert_keyframe at 10 + move (2x launches)")
        r = asyncio.run(kf_tools.handle_insert_keyframe({
            "fla_path": str(fla), "layer_name": "BG", "frame": 10,
        }))
        if json.loads(r[0].text).get("status") != "ok":
            _step("insert_keyframe", False, r[0].text); return 5
        r = asyncio.run(sym_tools.handle_set_instance_position({
            "fla_path": str(fla), "layer_name": "BG", "frame": 10,
            "x": 200, "y": 100,
        }))
        if json.loads(r[0].text).get("status") != "ok":
            _step("set_instance_position", False, r[0].text); return 6
        _step("setup motion (keyframe + position)", True)

        # 3. render_to_mp4 full timeline
        _print("  ... render_to_mp4 (Animate launches + ffmpeg encode)")
        r = asyncio.run(cam_tools.handle_render_to_mp4({
            "fla_path": str(fla),
            "out_path": str(full_mp4),
            "fps": 25,
        }))
        payload = json.loads(r[0].text)
        if payload.get("status") != "ok":
            _step("render_to_mp4", False, json.dumps(payload)); return 7
        full_size = payload.get("out_size_bytes", 0)
        full_frames = payload.get("frame_count", 0)
        if not full_mp4.exists() or full_size <= 0:
            _step("render_to_mp4 produced MP4", False,
                  f"out_path={full_mp4} size={full_size}")
            return 8
        _step(
            "render_to_mp4",
            True,
            f"{full_size} bytes, {full_frames} frames in {payload['elapsed_seconds']}s",
        )

        # 4. render_preview frames 1-5 (smaller render)
        _print("  ... render_preview frames 1-5 (Animate launches + encode)")
        r = asyncio.run(cam_tools.handle_render_preview({
            "fla_path": str(fla),
            "out_path": str(preview_mp4),
            "start_frame": 1,
            "end_frame": 5,
            "fps": 25,
        }))
        payload = json.loads(r[0].text)
        if payload.get("status") != "ok":
            _step("render_preview", False, json.dumps(payload)); return 9
        preview_size = payload.get("out_size_bytes", 0)
        preview_frames = payload.get("frame_count", 0)
        if not preview_mp4.exists() or preview_size <= 0:
            _step("render_preview produced MP4", False,
                  f"out_path={preview_mp4} size={preview_size}")
            return 10
        _step(
            "render_preview",
            True,
            f"{preview_size} bytes, {preview_frames} frames",
        )

        # Sanity: preview should be smaller / fewer frames than full
        if preview_frames > full_frames:
            _step(
                "preview frames <= full frames",
                False,
                f"preview={preview_frames} full={full_frames}",
            )
            return 11
        _step(
            "preview frames <= full frames",
            True,
            f"preview={preview_frames} full={full_frames}",
        )

        # 5. set_camera_position — experimental, non-fatal
        _print("  ... set_camera_position (experimental, Animate launch)")
        r = asyncio.run(cam_tools.handle_set_camera_position({
            "fla_path": str(fla),
            "frame": 1,
            "x": 50, "y": 50, "zoom": 1.5, "rotation": 0,
        }))
        payload = json.loads(r[0].text)
        if payload.get("status") == "ok":
            _step("set_camera_position (experimental)", True, f"{payload['elapsed_seconds']}s")
        else:
            _step(
                "set_camera_position (experimental, non-fatal)",
                True,
                f"experimental — did not pass cleanly: {payload.get('error', '?')}",
            )

    _print("")
    _print("All Phase 3i smoke steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
