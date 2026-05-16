"""End-to-end smoke for Phase 3d symbol-placement tools.

Run manually:
    <python> animate_cc_pipeline/tests/_smoke_phase3d.py

What this proves:
1. create_document + import_image_as_layer (Phase 3c, sets up the
   .fla with one element on layer "BG" at frame 1)
2. set_instance_position moves the element to (500, 300)
3. set_instance_scale scales it 2.0x
4. set_instance_rotation rotates it 45°
5. Reopen the .fla and verify the element's transform survived save

Wall time ~90-130s (5 Animate launches at ~15-20s each, plus a
verification re-open).

Animate.exe will visibly open + close multiple times — expected.
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

    img = Image.new("RGB", (32, 32), color=(20, 200, 120))
    img.save(path, format="PNG")


def main() -> int:
    _print("=" * 60)
    _print("Phase 3d smoke test")
    _print("=" * 60)

    try:
        from animate_cc_pipeline.mcp_server.tools import document as doc_tools
        from animate_cc_pipeline.mcp_server.tools import symbol as sym_tools
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

    with tempfile.TemporaryDirectory(prefix="animate_smoke3d_") as tmp:
        tmp_dir = Path(tmp)
        fla = tmp_dir / "phase3d.fla"
        png = tmp_dir / "tile.png"

        # Fixture
        try:
            _make_test_png(png)
        except Exception as exc:
            _step("generate test PNG", False, str(exc))
            return 3
        _step("generate test PNG", True, f"{png.stat().st_size} bytes")

        # 1. Setup: create_document
        _print("  ... create_document (Animate launch ~20s)")
        result = asyncio.run(doc_tools.handle_create_document({
            "fla_path": str(fla),
            "width": 1920,
            "height": 1080,
            "fps": 25,
        }))
        payload = json.loads(result[0].text)
        if payload.get("status") != "ok":
            _step("create_document", False, json.dumps(payload))
            return 4
        _step("create_document", True, f"{payload['elapsed_seconds']}s")

        # 2. Setup: import_image_as_layer (gives us layer "BG" with one element)
        _print("  ... import_image_as_layer (Animate launch ~17s)")
        result = asyncio.run(doc_tools.handle_import_image_as_layer({
            "fla_path": str(fla),
            "image_path": str(png),
            "layer_name": "BG",
            "frame": 1,
        }))
        payload = json.loads(result[0].text)
        if payload.get("status") != "ok":
            _step("import_image_as_layer", False, json.dumps(payload))
            return 5
        _step("import_image_as_layer", True, f"{payload['elapsed_seconds']}s")

        # Apply transforms in this order: rotation → scale → position.
        # Position LAST is important: in Animate's JSFL, element.x/y
        # refers to the element's bounding-box top-left, which shifts
        # under rotation/scale. Setting position last makes the final
        # x/y readable exactly. Production orchestrator should follow
        # the same convention.

        # 3. set_instance_rotation FIRST
        _print("  ... set_instance_rotation to 45 deg (Animate launch ~17s)")
        result = asyncio.run(sym_tools.handle_set_instance_rotation({
            "fla_path": str(fla),
            "layer_name": "BG",
            "frame": 1,
            "angle": 45,
        }))
        payload = json.loads(result[0].text)
        if payload.get("status") != "ok":
            _step("set_instance_rotation", False, json.dumps(payload))
            return 6
        _step("set_instance_rotation", True, f"{payload['elapsed_seconds']}s")

        # 4. set_instance_scale
        _print("  ... set_instance_scale to (2.0, 2.0) (Animate launch ~17s)")
        result = asyncio.run(sym_tools.handle_set_instance_scale({
            "fla_path": str(fla),
            "layer_name": "BG",
            "frame": 1,
            "sx": 2.0,
            "sy": 2.0,
        }))
        payload = json.loads(result[0].text)
        if payload.get("status") != "ok":
            _step("set_instance_scale", False, json.dumps(payload))
            return 7
        _step("set_instance_scale", True, f"{payload['elapsed_seconds']}s")

        # 5. set_instance_position LAST
        _print("  ... set_instance_position to (500, 300) (Animate launch ~17s)")
        result = asyncio.run(sym_tools.handle_set_instance_position({
            "fla_path": str(fla),
            "layer_name": "BG",
            "frame": 1,
            "x": 500,
            "y": 300,
        }))
        payload = json.loads(result[0].text)
        if payload.get("status") != "ok":
            _step("set_instance_position", False, json.dumps(payload))
            return 8
        _step("set_instance_position", True, f"{payload['elapsed_seconds']}s")

        # 6. Verification: reopen the .fla and read back the element transform
        _print("  ... reopen + verify transform survived (Animate launch ~17s)")
        verify_result_path = tmp_dir / "verify.json"
        sentinel = tmp_dir / "verify.sentinel"
        verify_template = _REPO_ROOT / "animate_cc_pipeline" / "tests" / "_verify_phase3d.jsfl"
        if not verify_template.exists():
            _step("verify template missing", False, str(verify_template))
            return 9

        result = jsfl_bridge.run_jsfl_template(
            verify_template,
            substitutions={
                "FLA_PATH": str(fla).replace("\\", "/"),
                "OUT_JSON_PATH": str(verify_result_path).replace("\\", "/"),
                "SENTINEL_PATH": str(sentinel).replace("\\", "/"),
            },
            expected_outputs=[verify_result_path, sentinel],
            poll_timeout=180.0,
        )
        if not result.completed_normally or not verify_result_path.exists():
            _step("verification reopen", False,
                  f"completed_normally={result.completed_normally}; missing={result.missing_outputs}")
            return 10

        readback = json.loads(verify_result_path.read_text(encoding="utf-8"))
        # Tolerances:
        #  - Position: ±2px (after rotation/scale, Animate's element.x/y
        #    reflects the post-transform bounding-box top-left which has
        #    small float-rounding drift even when position was set last).
        #  - Scale: ±0.01 (float drift)
        #  - Rotation: ±0.1 (float drift)
        x_ok = abs(readback.get("x", 0) - 500) < 2.0
        y_ok = abs(readback.get("y", 0) - 300) < 2.0
        sx_ok = abs(readback.get("scaleX", 0) - 2.0) < 0.01
        sy_ok = abs(readback.get("scaleY", 0) - 2.0) < 0.01
        rot_ok = abs(readback.get("rotation", 0) - 45.0) < 0.1

        _step("readback.x == 500", x_ok, f"got {readback.get('x')}")
        _step("readback.y == 300", y_ok, f"got {readback.get('y')}")
        _step("readback.scaleX == 2.0", sx_ok, f"got {readback.get('scaleX')}")
        _step("readback.scaleY == 2.0", sy_ok, f"got {readback.get('scaleY')}")
        _step("readback.rotation == 45", rot_ok, f"got {readback.get('rotation')}")

        if not all([x_ok, y_ok, sx_ok, sy_ok, rot_ok]):
            return 11

    _print("")
    _print("All Phase 3d smoke steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
