"""End-to-end smoke for Phase 3f bone/graphic + rig validator.

Run manually:
    <python> animate_cc_pipeline/tests/_smoke_phase3f.py

What this proves:
1. create_document
2. Programmatic Graphic Symbol creation: a "RotationStrip" Graphic
   with 3 blank keyframes, placed on layer "ARM" at frame 1.
3. get_graphic_first_frame("ARM", 1) → reports the instance state.
4. set_graphic_first_frame("ARM", 1, target=2, loop="single frame")
5. get_graphic_first_frame → firstFrame=2, loop="single frame".
6. validate_rig on the test .fla → expect FAIL with structured
   missing-RIG_SPEC_v1-field errors. Validates the validator's
   negative-path output.

Wall time ~130-180s (6 Animate launches).
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


def main() -> int:
    _print("=" * 60)
    _print("Phase 3f smoke test")
    _print("=" * 60)

    try:
        from animate_cc_pipeline.mcp_server.tools import document as doc_tools
        from animate_cc_pipeline.mcp_server.tools import bone as bone_tools
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

    with tempfile.TemporaryDirectory(prefix="animate_smoke3f_") as tmp:
        tmp_dir = Path(tmp)
        fla = tmp_dir / "phase3f.fla"
        setup_sentinel = tmp_dir / "setup.sentinel"

        # 1. create_document
        _print("  ... create_document (Animate launch)")
        result = asyncio.run(doc_tools.handle_create_document({
            "fla_path": str(fla), "width": 1920, "height": 1080, "fps": 25,
        }))
        if json.loads(result[0].text).get("status") != "ok":
            _step("create_document", False, result[0].text)
            return 3
        _step("create_document", True)

        # 2. Setup: build the Graphic Symbol "RotationStrip" + place instance
        setup_template = (
            _REPO_ROOT / "animate_cc_pipeline" / "mcp_server"
            / "jsfl_templates" / "_setup_phase3f_test_fla.jsfl"
        )
        _print("  ... build RotationStrip Graphic + place instance (Animate launch)")
        setup_result = jsfl_bridge.run_jsfl_template(
            setup_template,
            substitutions={
                "FLA_PATH": str(fla).replace("\\", "/"),
                "SENTINEL_PATH": str(setup_sentinel).replace("\\", "/"),
            },
            expected_outputs=[setup_sentinel],
            poll_timeout=180.0,
        )
        if not setup_result.completed_normally:
            _step("setup_fixture", False, f"setup JSFL failed; missing={setup_result.missing_outputs}")
            return 4
        _step("setup_fixture", True, f"{setup_result.elapsed_seconds:.1f}s")

        # 3. get_graphic_first_frame BEFORE setting — sanity baseline
        _print("  ... get_graphic_first_frame BEFORE set (Animate launch)")
        result = asyncio.run(bone_tools.handle_get_graphic_first_frame({
            "fla_path": str(fla), "layer_name": "ARM", "frame": 1,
        }))
        payload = json.loads(result[0].text)
        if payload.get("status") != "ok":
            _step("get_graphic_first_frame (before)", False, json.dumps(payload))
            return 5
        if not payload.get("found"):
            _step("get_graphic_first_frame (before)", False,
                  f"no element found on ARM frame 1: {payload}")
            return 6
        _step(
            "get_graphic_first_frame (before)",
            True,
            f"firstFrame={payload.get('firstFrame')}, loop={payload.get('loop')}, instanceType={payload.get('instanceType')}",
        )

        # 4. set_graphic_first_frame to target=2 + single frame
        _print("  ... set_graphic_first_frame target=2 loop=single frame (Animate launch)")
        result = asyncio.run(bone_tools.handle_set_graphic_first_frame({
            "fla_path": str(fla), "layer_name": "ARM", "frame": 1,
            "target_first_frame": 2, "loop_mode": "single frame",
        }))
        payload = json.loads(result[0].text)
        if payload.get("status") != "ok":
            _step("set_graphic_first_frame", False, json.dumps(payload))
            return 7
        _step("set_graphic_first_frame", True, f"{payload['elapsed_seconds']}s")

        # 5. get_graphic_first_frame AFTER — verify round-trip
        _print("  ... get_graphic_first_frame AFTER set (Animate launch)")
        result = asyncio.run(bone_tools.handle_get_graphic_first_frame({
            "fla_path": str(fla), "layer_name": "ARM", "frame": 1,
        }))
        payload = json.loads(result[0].text)
        if payload.get("status") != "ok":
            _step("get_graphic_first_frame (after)", False, json.dumps(payload))
            return 8

        first_frame = payload.get("firstFrame")
        loop = payload.get("loop")
        ok_ff = (first_frame == 2)
        ok_loop = (loop == "single frame")
        _step("readback.firstFrame == 2", ok_ff, f"got {first_frame}")
        _step("readback.loop == 'single frame'", ok_loop, f"got {loop!r}")
        if not (ok_ff and ok_loop):
            return 9

        # 6. validate_rig — should FAIL since the test .fla isn't a real
        # RIG_SPEC_v1 rig. We exercise the validator's negative path.
        _print("  ... validate_rig (expect FAIL — test fla is not a real rig) (Animate launch)")
        result = asyncio.run(bone_tools.handle_validate_rig({
            "fla_path": str(fla), "identity": "JETHALAL",
        }))
        payload = json.loads(result[0].text)
        # We expect status == "validation_failed" (not "error" or "ok")
        if payload.get("status") not in ("ok", "validation_failed"):
            _step("validate_rig", False, f"unexpected status: {json.dumps(payload)[:200]}")
            return 10
        passed = payload.get("passed", False)
        failure_count = payload.get("failure_count", 0)
        if passed:
            _step("validate_rig fails on bad rig",
                  False, "validator reported PASS on a non-rig .fla")
            return 11
        if failure_count < 4:
            _step("validate_rig fails on bad rig",
                  False, f"expected several failures, got {failure_count}")
            return 12
        _step("validate_rig fails on bad rig",
              True, f"{failure_count} rules failed (as expected)")

    _print("")
    _print("All Phase 3f smoke steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
