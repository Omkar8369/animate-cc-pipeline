"""CLI for camera move detection.

Usage:
  python -m animate_cc_pipeline.pipeline.cli_camera_detector \\
      --frames-dir <path> \\
      --shot-id    <id> \\
      --out        <path/to/camera_moves.json>

The frames-dir should contain `frame_NNNN.png` files (zero-padded,
1-indexed) — the convention Node 3 from the prior project produces.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .camera_detector import detect_camera_moves_from_frames


logger = logging.getLogger("cli_camera_detector")


def _collect_frames(frames_dir: Path) -> list[Path]:
    """Find frame_NNNN.png files in sorted order."""
    candidates = sorted(frames_dir.glob("frame_*.png"))
    if not candidates:
        # Fallback: any *.png
        candidates = sorted(frames_dir.glob("*.png"))
    return candidates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cli_camera_detector",
        description="Detect camera moves (pans) from a frame sequence.",
    )
    parser.add_argument("--frames-dir", type=Path, required=True,
                        help="Directory containing frame_NNNN.png files")
    parser.add_argument("--shot-id", type=str, required=True)
    parser.add_argument("--out", type=Path, required=True,
                        help="Output path for camera_moves.json")
    parser.add_argument("--confidence-floor", type=float, default=0.05,
                        help="Detections below this confidence are zeroed (default 0.05)")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARN", "ERROR"])
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if not args.frames_dir.exists() or not args.frames_dir.is_dir():
        logger.error("frames-dir does not exist or is not a directory: %s", args.frames_dir)
        return 2

    frame_paths = _collect_frames(args.frames_dir)
    if not frame_paths:
        logger.error("no PNG frames found in %s", args.frames_dir)
        return 2

    logger.info("detecting camera moves across %d frames", len(frame_paths))
    moves_map = detect_camera_moves_from_frames(
        frame_paths,
        shot_id=args.shot_id,
        confidence_floor=args.confidence_floor,
    )

    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(moves_map.model_dump_json(indent=2), encoding="utf-8")
        logger.info("wrote %s (%d frames)", args.out, moves_map.frame_count)
    except OSError as exc:
        logger.error("could not write %s: %s", args.out, exc)
        return 2

    final = moves_map.moves[-1] if moves_map.moves else None
    if final:
        logger.info(
            "final camera position: x=%.1f y=%.1f (cumulative shift over %d frames)",
            final.x, final.y, moves_map.frame_count,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
