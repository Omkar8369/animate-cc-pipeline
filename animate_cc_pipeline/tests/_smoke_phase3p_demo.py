"""End-to-end smoke for Phase 3p-demo: first real MP4.

Demonstrates the FULL pipeline against a real production rig:
  1. create_document   — fresh 1920x1080 .fla
  2. import_character_rig — pulls Jethalal's "front" pose via the
                            sidecar resolver (identity "front" →
                            obfuscated "NHNNFGH") + clipCopy/clipPaste
  3. save_document     — confirms .fla is well-formed
  4. render_to_mp4     — emits the .fla as an MP4 video

If this passes, the pipeline has produced its FIRST real MP4 with
a real TMKOC character. That's the milestone Phase 3p-validation
gates on. Subsequent shots add pose_map, background, audio etc.

Run manually:
    <python> animate_cc_pipeline/tests/_smoke_phase3p_demo.py

Wall time: ~3-4 minutes (4 Animate boots at ~30-60s each).

Output goes to `work/phase3p_demo/`:
  - jethalal_demo.fla   (target document)
  - jethalal_demo.mp4   (rendered video)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# sys.path fixup for standalone use
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _print(line: str) -> None:
    print(line, flush=True)


def _step(name: str, ok: bool, detail: str = "") -> None:
    icon = "OK  " if ok else "FAIL"
    _print(f"  [{icon}] {name}" + (f" - {detail}" if detail else ""))


DEFAULT_RIG_PATH = Path(
    r"C:\Users\Omkar Hajare\Downloads\CHARACTER\CHARACTER"
    r"\JETHALAL_Turnaround_FINAL.fla"
)


async def run_demo(rig_fla: Path, work_dir: Path) -> int:
    from animate_cc_pipeline.mcp_server.tools import (
        document as document_tools,
        camera as camera_tools,
    )

    rig_fla = rig_fla.resolve()
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    target_fla = work_dir / "jethalal_demo.fla"
    target_mp4 = work_dir / "jethalal_demo.mp4"
    # Clear any prior artifacts so the size checks are clean.
    for p in (target_fla, target_mp4):
        if p.exists():
            p.unlink()

    _print("=" * 64)
    _print(" Phase 3p-demo: FIRST REAL MP4 from the pipeline")
    _print("=" * 64)
    _print(f" rig:    {rig_fla}")
    _print(f" target: {target_fla}")
    _print(f" mp4:    {target_mp4}")
    _print("=" * 64)

    if not rig_fla.exists():
        _step("rig_exists", False, f"not at {rig_fla}")
        return 1
    _step("rig_exists", True, f"{rig_fla.stat().st_size // 1024 // 1024} MB")

    # ─── 1. create_document ──────────────────────────────────────
    _print("\n[1/4] create_document (1920x1080 @ 25fps)... ~25s")
    result = await document_tools.handle_create_document({
        "fla_path": str(target_fla),
        "width": 1920,
        "height": 1080,
        "fps": 25,
    })
    payload = json.loads(result[0].text)
    if payload.get("status") != "ok":
        _step("create_document", False, payload.get("error", "?"))
        return 1
    _step("create_document", True, f"{target_fla.stat().st_size / 1024:.1f} KB")

    # ─── 2. import_character_rig ─────────────────────────────────
    _print("\n[2/4] import_character_rig (Jethalal front pose)... ~40s")
    result = await document_tools.handle_import_character_rig({
        "fla_path": str(target_fla),
        "rig_fla_path": str(rig_fla),
        "identity": "front",  # sidecar resolves to "NHNNFGH"
        "layer_name": "JETHALAL",
        "frame": 1,
        "x": 960,
        "y": 540,
    })
    payload = json.loads(result[0].text)
    if payload.get("status") != "ok":
        _step("import_character_rig", False, payload.get("error", "?"))
        diag = payload.get("diagnostic_log", "")
        if diag:
            _print("\nJSFL diag log:")
            _print(diag)
        return 1
    instance_placed = payload.get("instance_placed", False)
    if not instance_placed:
        _step("import_character_rig", False, "instance not placed")
        return 1
    fla_size_mb = target_fla.stat().st_size / 1024 / 1024
    _step("import_character_rig", True,
          f"resolved={payload.get('resolved_identity', '?')}, "
          f".fla size {fla_size_mb:.2f} MB")

    # ─── 3. save_document (integrity round-trip) ────────────────
    _print("\n[3/4] save_document... ~20s")
    result = await document_tools.handle_save_document({
        "fla_path": str(target_fla),
    })
    payload = json.loads(result[0].text)
    if payload.get("status") != "ok":
        _step("save_document", False, payload.get("error", "?"))
        return 1
    _step("save_document", True, "integrity round-trip ok")

    # ─── 4. render_to_mp4 ───────────────────────────────────────
    _print("\n[4/4] render_to_mp4 (single frame at 25fps)... ~60s")
    result = await camera_tools.handle_render_to_mp4({
        "fla_path": str(target_fla),
        "out_path": str(target_mp4),
        "fps": 25,
    })
    payload = json.loads(result[0].text)
    if payload.get("status") != "ok":
        _step("render_to_mp4", False, payload.get("error", "?"))
        return 1
    if not target_mp4.exists() or target_mp4.stat().st_size == 0:
        _step("render_to_mp4", False, "MP4 missing or empty")
        return 1
    mp4_size_kb = target_mp4.stat().st_size / 1024
    frame_count = payload.get("frame_count", "?")
    _step("render_to_mp4", True,
          f"{mp4_size_kb:.1f} KB, {frame_count} frames")

    _print("\n" + "=" * 64)
    _print(" PHASE 3p-DEMO COMPLETE")
    _print(f" Open this MP4 to see the result:")
    _print(f"   {target_mp4}")
    _print(f" Open the .fla in Animate to inspect the timeline:")
    _print(f"   {target_fla}")
    _print("=" * 64)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_smoke_phase3p_demo",
        description="Phase 3p-demo: produce the pipeline's first real MP4",
    )
    parser.add_argument(
        "--rig", type=Path,
        default=Path(os.environ.get("PHASE3P_RIG_FLA", str(DEFAULT_RIG_PATH))),
        help="Path to the rig .fla (default: Jethalal turnaround)",
    )
    parser.add_argument(
        "--work-dir", type=Path,
        default=_REPO_ROOT / "work" / "phase3p_demo",
        help="Directory for the demo artifacts (.fla + .mp4)",
    )
    args = parser.parse_args(argv)
    return asyncio.run(run_demo(args.rig, args.work_dir))


if __name__ == "__main__":
    sys.exit(main())
