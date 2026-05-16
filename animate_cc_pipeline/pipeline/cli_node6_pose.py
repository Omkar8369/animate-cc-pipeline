"""Node 6 CLI: per-frame pose estimation.

Reads per-shot bbox detections (node5_result.json + per-shot
character_map.json) + per-shot frames; runs each detection through
a configurable pose backend; writes:

  <work_dir>/<shot_id>/pose_map.json   per shot
  <work_dir>/node6_result.json         aggregate

Usage:
  python -m animate_cc_pipeline.pipeline.cli_node6_pose \\
      --node5-result <path> \\
      --frames-root  <path> \\
      --work-dir     <path> \\
      --backend      mock|http|dwpose_local \\
      [--http-url    URL]

CLI exit codes:
  0 — success
  1 — Node6Error subclass (input I/O, schema, backend show-stopper)
  2 — unexpected exception
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np

from .errors import (
    Node6Error,
    Node5ResultInputError,
    FramesDirInputError,
    PoseBackendError,
    PoseMapOutputError,
)
from .pose_estimator import PoseEstimator, get_pose_estimator
from .schemas import (
    Bbox,
    CharacterPose,
    FramePoseSet,
    JointSet,
    Node6Result,
    PoseMap,
    ShotPoseSummary,
)


logger = logging.getLogger("node6_pose")


# ─── Input loading ──────────────────────────────────────────────────


def _load_node5_result(path: Path) -> dict:
    if not path.exists():
        raise Node5ResultInputError(f"node5_result.json not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Node5ResultInputError(
            f"node5_result.json malformed: {exc}"
        ) from exc
    if data.get("schemaVersion") not in (1, "1"):
        raise Node5ResultInputError(
            f"node5_result.json schemaVersion must be 1; got {data.get('schemaVersion')!r}"
        )
    return data


def _load_character_map(shot_dir: Path) -> dict:
    """Load <shot>/character_map.json (Node 5's per-shot detections).

    Expected shape (informally — Node 5 from the prior project):
      {
        schemaVersion: 1,
        shotId: str,
        keyPoses: [
          {
            keyPoseIndex: int,
            sourceFrame: int,   # 1-indexed
            detections: [
              { identity: str, boundingBox: { x, y, w, h }, ... },
              ...
            ]
          },
          ...
        ]
      }
    """
    path = shot_dir / "character_map.json"
    if not path.exists():
        raise Node5ResultInputError(
            f"character_map.json missing in shot dir: {path}"
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Node5ResultInputError(
            f"character_map.json malformed: {exc}"
        ) from exc


def _load_frame(frames_dir: Path, frame_idx_1based: int) -> np.ndarray:
    """Load frame_NNNN.png as a HxWx3 numpy array."""
    candidates = [
        frames_dir / f"frame_{frame_idx_1based:04d}.png",
        frames_dir / f"frame_{frame_idx_1based:05d}.png",
        frames_dir / f"{frame_idx_1based:04d}.png",
    ]
    for cand in candidates:
        if cand.exists():
            return _png_to_array(cand)
    raise FramesDirInputError(
        f"frame {frame_idx_1based} not found in {frames_dir} "
        f"(tried: {[c.name for c in candidates]})"
    )


def _png_to_array(path: Path) -> np.ndarray:
    try:
        from PIL import Image  # type: ignore
    except ImportError as exc:
        raise FramesDirInputError(
            "Pillow required for frame loading; install via pip"
        ) from exc
    img = Image.open(str(path)).convert("RGB")
    return np.asarray(img)


# ─── Core pipeline ──────────────────────────────────────────────────


def _build_character_pose(
    estimator: PoseEstimator,
    image: np.ndarray,
    identity: str,
    bbox_dict: dict[str, int],
) -> CharacterPose | None:
    """Run the estimator on one character; return a CharacterPose or
    None on backend failure (logged + soft-skipped).
    """
    try:
        bbox = Bbox(
            x=int(bbox_dict["x"]),
            y=int(bbox_dict["y"]),
            w=int(bbox_dict["w"]),
            h=int(bbox_dict["h"]),
        )
    except (KeyError, ValueError) as exc:
        logger.warning("invalid bbox for %s: %s; skipping", identity, exc)
        return None

    try:
        joints = estimator.estimate_pose(image, bbox)
    except PoseBackendError as exc:
        logger.warning("backend failed on %s frame: %s; setting joints=None", identity, exc)
        joints = JointSet()  # all-None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("unexpected estimator error on %s: %s; skipping", identity, exc)
        return None

    return CharacterPose(identity=identity, bbox=bbox, joints=joints)


def process_shot(
    estimator: PoseEstimator,
    shot_id: str,
    frames_dir: Path,
    character_map: dict,
    pose_map_out_path: Path,
) -> ShotPoseSummary:
    """Process one shot end-to-end. Writes pose_map.json; returns summary."""

    keyposes = character_map.get("keyPoses", [])
    # Build {1-indexed frame: [(identity, bbox), ...]} from keypose + held frames.
    # For Phase 3j v1 we treat each keypose's sourceFrame as the frame
    # the bbox applies to. Held-frame interpolation is the orchestrator's
    # job (Phase 3l) — Node 6 just emits poses for the keypose frames.
    frame_detections: dict[int, list[tuple[str, dict]]] = {}
    for kp in keyposes:
        frame_idx = int(kp.get("sourceFrame", 0))
        if frame_idx < 1:
            continue
        for det in kp.get("detections", []):
            identity = det.get("identity", "")
            bbox = det.get("boundingBox") or det.get("bbox")
            if not identity or not bbox:
                continue
            frame_detections.setdefault(frame_idx, []).append((identity, bbox))

    pose_map = PoseMap(schemaVersion=1, shotId=shot_id, frames={})
    characters_found = 0

    for frame_idx in sorted(frame_detections):
        try:
            image = _load_frame(frames_dir, frame_idx)
        except FramesDirInputError as exc:
            logger.warning("skipping frame %d: %s", frame_idx, exc)
            continue
        frame_set = FramePoseSet(frameIndex=frame_idx, characters=[])
        for identity, bbox_dict in frame_detections[frame_idx]:
            cp = _build_character_pose(estimator, image, identity, bbox_dict)
            if cp is not None:
                frame_set.characters.append(cp)
                characters_found += 1
        pose_map.frames[str(frame_idx)] = frame_set

    # Write per-shot pose_map.json
    try:
        pose_map_out_path.parent.mkdir(parents=True, exist_ok=True)
        pose_map_out_path.write_text(
            pose_map.model_dump_json(indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        raise PoseMapOutputError(
            f"could not write {pose_map_out_path}: {exc}"
        ) from exc

    return ShotPoseSummary(
        shotId=shot_id,
        framesProcessed=len(pose_map.frames),
        charactersFound=characters_found,
        poseMapPath=str(pose_map_out_path.resolve()),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cli_node6_pose",
        description="Per-frame pose estimation for the animatic-refinement pipeline.",
    )
    parser.add_argument("--node5-result", type=Path, required=True,
                        help="Path to node5_result.json (Node 5's per-shot detection output)")
    parser.add_argument("--frames-root", type=Path, required=True,
                        help="Path under which each shot's frames live (<frames-root>/<shotId>/frame_NNNN.png)")
    parser.add_argument("--work-dir", type=Path, required=True,
                        help="Output dir (per-shot pose_map.json + aggregate node6_result.json)")
    parser.add_argument("--backend", choices=["mock", "http", "dwpose_local"],
                        default="mock",
                        help="Pose backend (default: mock for testing)")
    parser.add_argument("--http-url", type=str, default=None,
                        help="Remote pose service URL (required for --backend=http)")
    parser.add_argument("--http-timeout", type=int, default=30,
                        help="HTTP timeout in seconds (default 30)")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARN", "ERROR"])
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    try:
        node5_result = _load_node5_result(args.node5_result)
        kwargs: dict[str, Any] = {}
        if args.backend == "http":
            if not args.http_url:
                logger.error("--http-url is required with --backend=http")
                return 1
            kwargs["url"] = args.http_url
            kwargs["timeout"] = args.http_timeout
        estimator = get_pose_estimator(args.backend, **kwargs)

        summaries: list[ShotPoseSummary] = []
        for shot in node5_result.get("shots", []):
            shot_id = shot.get("shotId")
            if not shot_id:
                logger.warning("skipping shot without shotId: %r", shot)
                continue
            shot_dir = args.frames_root / shot_id
            if not shot_dir.exists():
                logger.warning("shot dir missing for %s: %s; skipping", shot_id, shot_dir)
                continue
            character_map = _load_character_map(shot_dir)
            pose_map_path = args.work_dir / shot_id / "pose_map.json"
            summary = process_shot(
                estimator, shot_id, shot_dir, character_map, pose_map_path,
            )
            summaries.append(summary)
            logger.info(
                "shot %s: %d frames, %d character poses written -> %s",
                shot_id, summary.framesProcessed, summary.charactersFound, pose_map_path,
            )

        result = Node6Result(
            schemaVersion=1,
            backend=estimator.name,
            shots=summaries,
        )
        result_path = args.work_dir / "node6_result.json"
        try:
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        except OSError as exc:
            raise PoseMapOutputError(
                f"could not write {result_path}: {exc}"
            ) from exc

        logger.info(
            "Node 6 done: %d shot(s) processed; aggregate -> %s",
            len(summaries), result_path,
        )
        return 0

    except Node6Error as exc:
        logger.error("Node 6 error: %s", exc)
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected error: %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
