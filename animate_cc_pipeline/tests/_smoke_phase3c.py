"""End-to-end smoke for Phase 3c document tools.

Run manually:
    <python> animate_cc_pipeline/tests/_smoke_phase3c.py

What this proves:
1. create_document via MCP creates a real .fla
2. save_document round-trips through Animate cleanly
3. import_image_as_layer adds a layer + embeds a PIL-generated PNG
4. close_document cleans up any leftover Animate.exe
5. Final .fla exists, is non-trivially larger than the empty doc
   (showing the image was actually embedded)

Wall time: ~60-90 seconds (3-4 Animate launches at ~20-25s each).
Animate.exe will visibly open + close multiple times — this is
expected.

Skips video import (would require a small MP4 fixture); video tool
unit-tested via argument-validation tests and JSFL-template
existence tests.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

# sys.path fixup so this works as a standalone script
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _print(line: str) -> None:
    print(line, flush=True)


def _step(name: str, ok: bool, detail: str = "") -> None:
    icon = "OK  " if ok else "FAIL"
    _print(f"  [{icon}] {name}" + (f" - {detail}" if detail else ""))


def _make_test_png(path: Path) -> None:
    """Create a 16x16 solid-color PNG via PIL."""
    from PIL import Image  # type: ignore

    img = Image.new("RGB", (16, 16), color=(180, 60, 200))
    img.save(path, format="PNG")


def main() -> int:
    _print("=" * 60)
    _print("Phase 3c smoke test")
    _print("=" * 60)

    # 1. Imports
    try:
        from animate_cc_pipeline.mcp_server.tools import document as doc_tools
        from animate_cc_pipeline.mcp_server import jsfl_bridge
    except Exception as exc:
        _step("imports", False, str(exc))
        return 1
    _step("imports", True)

    # 2. Animate.exe resolution
    try:
        animate_exe = jsfl_bridge._resolve_animate_exe()
    except FileNotFoundError as exc:
        _step("resolve Animate.exe", False, str(exc).splitlines()[0])
        return 2
    _step("resolve Animate.exe", True, str(animate_exe))

    with tempfile.TemporaryDirectory(prefix="animate_smoke3c_") as tmp:
        tmp_dir = Path(tmp)
        fla = tmp_dir / "phase3c.fla"
        png = tmp_dir / "test_bg.png"

        # 3. Test fixture: tiny PNG
        try:
            _make_test_png(png)
        except Exception as exc:
            _step("generate test PNG", False, str(exc))
            return 3
        _step(
            "generate test PNG",
            True,
            f"{png.stat().st_size} bytes at {png.name}",
        )

        # 4. create_document
        _print("  ... create_document (Animate launches; ~20-25s)")
        result = asyncio.run(doc_tools.handle_create_document({
            "fla_path": str(fla),
            "width": 1920,
            "height": 1080,
            "fps": 25,
        }))
        payload = json.loads(result[0].text)
        if payload.get("status") != "ok" or not fla.exists():
            _step("create_document", False, json.dumps(payload))
            return 4
        empty_size = fla.stat().st_size
        _step(
            "create_document",
            True,
            f"{empty_size} bytes in {payload['elapsed_seconds']}s",
        )

        # 5. save_document (round-trip integrity)
        _print("  ... save_document (Animate launches; ~20-25s)")
        result = asyncio.run(doc_tools.handle_save_document({
            "fla_path": str(fla),
        }))
        payload = json.loads(result[0].text)
        if payload.get("status") != "ok":
            _step("save_document", False, json.dumps(payload))
            return 5
        _step(
            "save_document",
            True,
            f"{payload['elapsed_seconds']}s; .fla still exists",
        )

        # 6. import_image_as_layer
        _print("  ... import_image_as_layer (Animate launches; ~20-25s)")
        result = asyncio.run(doc_tools.handle_import_image_as_layer({
            "fla_path": str(fla),
            "image_path": str(png),
            "layer_name": "BG",
            "frame": 1,
        }))
        payload = json.loads(result[0].text)
        if payload.get("status") != "ok":
            _step("import_image_as_layer", False, json.dumps(payload))
            return 6
        after_import_size = fla.stat().st_size
        _step(
            "import_image_as_layer",
            True,
            f"fla grew from {empty_size} -> {after_import_size} bytes "
            f"in {payload['elapsed_seconds']}s",
        )
        if after_import_size <= empty_size:
            _step(
                ".fla grew after image import",
                False,
                f"size unchanged ({empty_size} bytes); image may not have embedded",
            )
            return 7

        # 7. close_document (cleanup)
        result = asyncio.run(doc_tools.handle_close_document({}))
        payload = json.loads(result[0].text)
        if payload.get("status") != "ok":
            _step("close_document", False, json.dumps(payload))
            return 8
        _step(
            "close_document",
            True,
            f"killed_running_animate={payload['killed']}",
        )

    _print("")
    _print("All Phase 3c smoke steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
