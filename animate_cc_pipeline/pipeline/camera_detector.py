"""Camera move detection — frame-correlation analysis.

Phase 3m: detects pans (translation) in a sequence of frames from
a rough animatic by phase-correlating consecutive frames. The
output `CameraMovesMap` is consumed by the orchestrator
(Phase 3m-fixup or 3n) to set Animate's Camera transform per
frame so the output MP4 mirrors the rough's camera work.

What's NOT detected in v1:
  - Zoom (would need scale-search at multiple resolutions)
  - Rotation (would need angle-search)
The CameraState schema reserves these fields with default values
so future detection backends can populate them without breaking
the consumer contract.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from pydantic import BaseModel, ConfigDict, Field


logger = logging.getLogger("camera_detector")


# ─── Schemas ──────────────────────────────────────────────────────


class CameraState(BaseModel):
    """Cumulative camera transform at a specific frame.

    Coordinates are in image pixels. (0, 0) for the FIRST frame —
    subsequent frames accumulate the per-pair deltas.
    """
    model_config = ConfigDict(extra="forbid")

    frame: int = Field(ge=1)  # 1-indexed
    x: float = 0.0
    y: float = 0.0
    zoom: float = 1.0
    rotation: float = 0.0
    confidence: float = Field(default=0.0, ge=0.0)


class CameraMovesMap(BaseModel):
    """Top-level camera_moves.json shape (one per shot)."""
    model_config = ConfigDict(extra="forbid")

    schemaVersion: int = Field(default=1, ge=1)
    shot_id: str
    frame_count: int = Field(ge=0)
    moves: list[CameraState] = Field(default_factory=list)


# ─── Detection ────────────────────────────────────────────────────


def _to_grayscale_float32(frame: np.ndarray) -> np.ndarray:
    """Convert HxWx3 RGB or HxW grayscale to float32 grayscale.

    Avoids importing cv2 at module-load time so non-vision users of
    the schemas don't pay the import cost.
    """
    if frame.ndim == 2:
        return frame.astype(np.float32)
    if frame.ndim == 3 and frame.shape[2] >= 3:
        # Standard luma weighting (Rec.601)
        r = frame[..., 0].astype(np.float32)
        g = frame[..., 1].astype(np.float32)
        b = frame[..., 2].astype(np.float32)
        return 0.299 * r + 0.587 * g + 0.114 * b
    raise ValueError(f"unexpected frame shape {frame.shape}")


def detect_translation(
    frame_a: np.ndarray,
    frame_b: np.ndarray,
) -> tuple[float, float, float]:
    """Detect the translation between two consecutive frames using
    phase correlation (FFT-based).

    Returns `(dx, dy, confidence)` where (dx, dy) is the translation
    in pixels that aligns frame_b to frame_a's coordinate frame, and
    confidence is the peak response of the cross-power spectrum
    (range roughly 0..1; higher = more reliable).

    Uses `cv2.phaseCorrelate`. If OpenCV is unavailable, falls back
    to a pure-numpy FFT phase-correlation implementation.
    """
    if frame_a.shape != frame_b.shape:
        raise ValueError(
            f"frame shapes must match for phase correlation; "
            f"got {frame_a.shape} vs {frame_b.shape}"
        )

    gray_a = _to_grayscale_float32(frame_a)
    gray_b = _to_grayscale_float32(frame_b)

    try:
        import cv2  # type: ignore
        (dx, dy), response = cv2.phaseCorrelate(gray_a, gray_b)
        return (float(dx), float(dy), float(response))
    except ImportError:
        return _phase_correlate_numpy(gray_a, gray_b)


def _phase_correlate_numpy(
    gray_a: np.ndarray, gray_b: np.ndarray
) -> tuple[float, float, float]:
    """Pure-numpy phase correlation fallback. Less accurate than
    cv2's sub-pixel implementation; rounds to integer pixel shifts."""
    fa = np.fft.fft2(gray_a)
    fb = np.fft.fft2(gray_b)
    cross_power = fa * np.conj(fb)
    eps = 1e-10
    cross_power /= np.abs(cross_power) + eps
    correlation = np.fft.ifft2(cross_power).real

    peak_idx = np.unravel_index(np.argmax(correlation), correlation.shape)
    h, w = gray_a.shape
    dy = peak_idx[0]
    dx = peak_idx[1]
    # Wrap negative shifts (FFT phase correlation wraps around)
    if dy > h // 2:
        dy -= h
    if dx > w // 2:
        dx -= w
    confidence = float(correlation.max() / (correlation.sum() + eps))
    return (float(dx), float(dy), confidence)


# ─── Frame loading ────────────────────────────────────────────────


def load_frame(path: Path | str) -> np.ndarray:
    """Load an image file as a HxWx3 RGB uint8 numpy array."""
    try:
        from PIL import Image  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "Pillow required for frame loading; install via pip"
        ) from exc
    img = Image.open(str(path)).convert("RGB")
    return np.asarray(img)


# ─── Pipeline ─────────────────────────────────────────────────────


def detect_camera_moves_from_frames(
    frame_paths: list[Path | str],
    shot_id: str,
    *,
    confidence_floor: float = 0.05,
) -> CameraMovesMap:
    """Detect camera moves across a sequence of frame paths.

    Args:
        frame_paths: ordered list of frame image paths (1-indexed
                     in the output by position in the list).
        shot_id: identifier embedded in the output JSON.
        confidence_floor: per-pair detections below this confidence
                          are treated as zero-movement (avoids
                          noise polluting the cumulative track).

    Returns: CameraMovesMap with one CameraState per input frame.
             Frame 1 always has x=0, y=0 (anchor); subsequent frames
             accumulate detected translations.
    """
    frame_paths = list(frame_paths)
    moves: list[CameraState] = []
    if not frame_paths:
        return CameraMovesMap(shot_id=shot_id, frame_count=0, moves=[])

    # Frame 1 is the anchor — no detection needed
    moves.append(CameraState(
        frame=1, x=0.0, y=0.0, zoom=1.0, rotation=0.0, confidence=1.0,
    ))
    prev_frame = load_frame(frame_paths[0])
    cum_x, cum_y = 0.0, 0.0

    for i, path in enumerate(frame_paths[1:], start=2):
        curr_frame = load_frame(path)
        try:
            dx, dy, conf = detect_translation(prev_frame, curr_frame)
        except Exception as exc:
            logger.warning("frame %d: detection failed (%s); zero-movement", i, exc)
            dx, dy, conf = 0.0, 0.0, 0.0

        if conf < confidence_floor:
            # Treat low-confidence detections as no movement; the
            # cumulative track is robust against noise that way.
            dx, dy = 0.0, 0.0

        cum_x += dx
        cum_y += dy
        moves.append(CameraState(
            frame=i, x=cum_x, y=cum_y, zoom=1.0, rotation=0.0, confidence=conf,
        ))
        prev_frame = curr_frame

    return CameraMovesMap(
        shot_id=shot_id,
        frame_count=len(frame_paths),
        moves=moves,
    )
