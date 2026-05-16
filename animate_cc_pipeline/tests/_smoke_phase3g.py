"""End-to-end smoke for Phase 3g tween tools.

Run manually:
    <python> animate_cc_pipeline/tests/_smoke_phase3g.py

What this proves:
1. Two keyframes are set up on layer "BG" (frame 1 with image,
   frame 30 with the image moved to a different position).
2. `add_classic_tween` at frame 1 → frame 1's tweenType becomes
   "motion".
3. `set_easing` at frame 1 to +50 → frame 1's tweenEasing == 50.
4. `_verify_phase3g.jsfl` reads back both properties; smoke asserts
   they survived save/reopen.
5. `add_motion_tween` attempted as an experimental step — recorded
   but not gated. If it errors on Animate 2020, documented as a
   deferred bug.

Wall time ~130-180s (7-8 Animate launches).
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

    img = Image.new("RGB", (32, 32), color=(80, 160, 240))
    img.save(path, format="PNG")


def _verify_tween(jsfl_bridge, fla: Path, layer: str, frame: int) -> dict:
    """Run the verify helper, return parsed JSON readback."""
    out_json = fla.with_suffix(fla.suffix + ".verify.json")
    sentinel = out_json.with_suffix(out_json.suffix + ".sentinel")
    for p in (out_json, sentinel):
        try:
            p.unlink()
        except (OSError, FileNotFoundError):
            pass
    verify_template = (
        _REPO_ROOT / "animate_cc_pipeline" / "tests" / "_verify_phase3g.jsfl"
    )
    result = jsfl_bridge.run_jsfl_template(
        verify_template,
        substitutions={
            "FLA_PATH": str(fla).replace("\\", "/"),
            "LAYER_NAME": layer,
            "FRAME": frame,
            "OUT_JSON_PATH": str(out_json).replace("\\", "/"),
            "SENTINEL_PATH": str(sentinel).replace("\\", "/"),
        },
        expected_outputs=[out_json, sentinel],
        poll_timeout=180.0,
    )
    if not result.completed_normally or not out_json.exists():
        return {"error": "verify JSFL did not complete", "missing": result.missing_outputs}
    try:
        data = json.loads(out_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"error": f"invalid JSON from verify: {exc}"}
    finally:
        for p in (out_json, sentinel):
            try:
                p.unlink()
            except (OSError, FileNotFoundError):
                pass
    return data


def main() -> int:
    _print("=" * 60)
    _print("Phase 3g smoke test")
    _print("=" * 60)

    try:
        from animate_cc_pipeline.mcp_server.tools import document as doc_tools
        from animate_cc_pipeline.mcp_server.tools import keyframe as kf_tools
        from animate_cc_pipeline.mcp_server.tools import symbol as sym_tools
        from animate_cc_pipeline.mcp_server.tools import tween as tw_tools
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

    with tempfile.TemporaryDirectory(prefix="animate_smoke3g_") as tmp:
        tmp_dir = Path(tmp)
        fla = tmp_dir / "phase3g.fla"
        png = tmp_dir / "tile.png"
        _make_test_png(png)

        # 1. Setup: create doc + import image (gets us keyframe at frame 1)
        _print("  ... create_document + import_image_as_layer (2x Animate launches)")
        r = asyncio.run(doc_tools.handle_create_document({
            "fla_path": str(fla), "width": 1920, "height": 1080, "fps": 25,
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

        # 2. insert_keyframe at frame 30 (need 2 keyframes to tween between)
        _print("  ... insert_keyframe at 30 (Animate launch)")
        r = asyncio.run(kf_tools.handle_insert_keyframe({
            "fla_path": str(fla), "layer_name": "BG", "frame": 30,
        }))
        if json.loads(r[0].text).get("status") != "ok":
            _step("insert_keyframe", False, r[0].text); return 5
        _step("insert_keyframe at 30", True)

        # 3. Move the instance at frame 30 to create actual motion
        _print("  ... set_instance_position at frame 30 (Animate launch)")
        r = asyncio.run(sym_tools.handle_set_instance_position({
            "fla_path": str(fla), "layer_name": "BG", "frame": 30,
            "x": 500, "y": 300,
        }))
        if json.loads(r[0].text).get("status") != "ok":
            _step("set_instance_position", False, r[0].text); return 6
        _step("set_instance_position at 30", True)

        # 4. add_classic_tween at frame 1
        _print("  ... add_classic_tween at frame 1 (Animate launch)")
        r = asyncio.run(tw_tools.handle_add_classic_tween({
            "fla_path": str(fla), "layer_name": "BG", "start_frame": 1,
        }))
        payload = json.loads(r[0].text)
        if payload.get("status") != "ok":
            _step("add_classic_tween", False, json.dumps(payload)); return 7
        _step("add_classic_tween", True, f"{payload['elapsed_seconds']}s")

        # 5. set_easing at frame 1 to +50
        _print("  ... set_easing at frame 1 to +50 (Animate launch)")
        r = asyncio.run(tw_tools.handle_set_easing({
            "fla_path": str(fla), "layer_name": "BG", "frame": 1, "easing": 50,
        }))
        payload = json.loads(r[0].text)
        if payload.get("status") != "ok":
            _step("set_easing", False, json.dumps(payload)); return 8
        _step("set_easing", True, f"{payload['elapsed_seconds']}s")

        # 6. Verify via _verify_phase3g.jsfl
        _print("  ... verify tween properties survived (Animate launch)")
        readback = _verify_tween(jsfl_bridge, fla, "BG", 1)
        if "error" in readback:
            _step("verify_tween", False, str(readback)); return 9
        if not readback.get("found"):
            _step("verify_tween found", False, json.dumps(readback)); return 10
        type_ok = readback.get("tweenType") == "motion"
        easing_ok = readback.get("tweenEasing") == 50
        _step("readback.tweenType == 'motion'", type_ok, f"got {readback.get('tweenType')!r}")
        _step("readback.tweenEasing == 50", easing_ok, f"got {readback.get('tweenEasing')}")
        if not (type_ok and easing_ok):
            return 11

        # 7. add_motion_tween — experimental; we record outcome but don't gate
        _print("  ... add_motion_tween (experimental, Animate launch)")
        r = asyncio.run(tw_tools.handle_add_motion_tween({
            "fla_path": str(fla), "layer_name": "BG",
            "start_frame": 1, "end_frame": 30,
        }))
        payload = json.loads(r[0].text)
        if payload.get("status") == "ok":
            _step("add_motion_tween (experimental)", True, f"{payload['elapsed_seconds']}s")
        else:
            _step(
                "add_motion_tween (experimental, non-fatal)",
                True,
                f"experimental — did not pass cleanly: {payload.get('error', 'unknown')}",
            )

    _print("")
    _print("All Phase 3g smoke steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
