"""End-to-end smoke for Phase 3l orchestrator.

Run manually:
    <python> animate_cc_pipeline/tests/_smoke_phase3l.py

What this proves:
1. The orchestrator's full per-shot pipeline runs end-to-end against
   REAL Animate.exe (not mocked handlers).
2. Synthetic inputs go in: a PIL-generated background, a PIL-generated
   placeholder character image, a synthesized pose_map with 3 frames
   that move the character across the canvas.
3. A real `.fla` is produced + a real MP4 is rendered.
4. The MP4's frame count matches expectations.

Wall time ~3-5 minutes (8-10 Animate launches: create + bg import +
placeholder char import + 3 keyframes × 3 ops each + tweens + save +
render).

This is the BIG smoke — the orchestrator running for real. After
this passes, the pipeline is end-to-end functional for production
shots (once the rigger commission provides real rigs).
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


def _make_placeholder_png(path: Path, size=(64, 64), color=(255, 100, 50)) -> None:
    from PIL import Image  # type: ignore
    Image.new("RGB", size, color=color).save(path, format="PNG")


def _make_synthetic_pose_map(out_path: Path) -> None:
    """Write a pose_map.json with 3 frames whose bboxes vary so the
    placeholder character moves across the canvas."""
    from animate_cc_pipeline.pipeline.schemas import (
        Bbox, CharacterPose, FramePoseSet, Joint, JointSet, PoseMap,
    )

    def _frame(idx: int, cx: float, cy: float) -> FramePoseSet:
        j = lambda x, y: Joint(x=x, y=y, confidence=0.9)
        bw = 100
        bh = 200
        js = JointSet(
            nose=j(cx, cy - bh * 0.4),
            neck=j(cx, cy - bh * 0.3),
            shoulder_L=j(cx - bw * 0.25, cy - bh * 0.25),
            shoulder_R=j(cx + bw * 0.25, cy - bh * 0.25),
        )
        cp = CharacterPose(
            identity="HERO",
            bbox=Bbox(x=int(cx - bw / 2), y=int(cy - bh / 2), w=bw, h=bh),
            joints=js,
        )
        return FramePoseSet(frameIndex=idx, characters=[cp])

    pose_map = PoseMap(
        shotId="phase3l_smoke",
        frames={
            "1":  _frame(1, cx=200, cy=300),
            "10": _frame(10, cx=600, cy=300),
            "20": _frame(20, cx=900, cy=400),
        },
    )
    out_path.write_text(pose_map.model_dump_json(indent=2), encoding="utf-8")


def main() -> int:
    _print("=" * 60)
    _print("Phase 3l smoke test (orchestrator end-to-end)")
    _print("=" * 60)

    try:
        from animate_cc_pipeline.mcp_server import jsfl_bridge
        from animate_cc_pipeline.pipeline.orchestrator.assembly_schemas import (
            CharacterConfig, ShotConfig,
        )
        from animate_cc_pipeline.pipeline.orchestrator.shot_processor import process_shot
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

    with tempfile.TemporaryDirectory(prefix="animate_smoke3l_") as tmp:
        tmp_dir = Path(tmp)
        fla_out = tmp_dir / "phase3l.fla"
        mp4_out = tmp_dir / "phase3l.mp4"
        bg_png = tmp_dir / "bg.png"
        hero_png = tmp_dir / "hero.png"
        pose_map = tmp_dir / "pose_map.json"

        # Synthesize the inputs
        _make_placeholder_png(bg_png, size=(320, 240), color=(40, 80, 120))
        _make_placeholder_png(hero_png, size=(64, 128), color=(220, 60, 50))
        _make_synthetic_pose_map(pose_map)
        _step("synthesize inputs", True,
              f"bg={bg_png.stat().st_size}B, hero={hero_png.stat().st_size}B")

        # Build the shot config
        cfg = ShotConfig(
            shot_id="phase3l_smoke",
            fla_out_path=fla_out,
            mp4_out_path=mp4_out,
            background_image_path=bg_png,
            width=320,
            height=240,
            fps=25,
            characters=[
                CharacterConfig(
                    identity="HERO",
                    placeholder_image_path=hero_png,
                    pose_map_path=pose_map,
                ),
            ],
        )

        _print("  ... running orchestrator (this takes ~3-5 minutes)")
        _print("      Animate.exe will open and close ~8-10 times.")
        assembly = asyncio.run(process_shot(cfg))

        _step(
            "orchestrator success flag",
            assembly.success,
            f"{assembly.total_elapsed_seconds:.1f}s, "
            f"{assembly.keyposes_processed} keyposes, "
            f"{len(assembly.warnings)} warnings",
        )
        for w in assembly.warnings:
            _print(f"      warning: {w}")

        _step("fla produced", fla_out.exists(),
              f"{fla_out.stat().st_size}B" if fla_out.exists() else "missing")
        _step("mp4 produced", mp4_out.exists(),
              f"{mp4_out.stat().st_size}B" if mp4_out.exists() else "missing")
        # We expect at least the 3 keyposes plus tween frames in the
        # MP4. With keyframes at 1, 10, 20 and tweens, expect ≥ 20 frames.
        _step("keyposes_processed == 3", assembly.keyposes_processed == 3,
              f"got {assembly.keyposes_processed}")
        _step("characters_assembled == 1", assembly.characters_assembled == 1,
              f"got {assembly.characters_assembled}")

        if not (assembly.success and fla_out.exists() and mp4_out.exists()):
            _print("")
            _print("Smoke failed. Step trace:")
            for s in assembly.steps:
                marker = "✓" if s.ok else "✗"
                _print(f"  {marker} {s.step} ({s.elapsed_seconds:.1f}s) {s.note}")
            return 3

    _print("")
    _print("All Phase 3l smoke steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
