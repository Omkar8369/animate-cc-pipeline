"""Unit tests for camera move detection.

Synthetic frames with KNOWN shifts (via np.roll) — we verify the
detector recovers the shift accurately.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from animate_cc_pipeline.pipeline.camera_detector import (
    CameraMovesMap,
    CameraState,
    _phase_correlate_numpy,
    _to_grayscale_float32,
    detect_camera_moves_from_frames,
    detect_translation,
    load_frame,
)


# ─── Helpers ──────────────────────────────────────────────────────


def _random_frame(rng: np.random.Generator, h=128, w=128) -> np.ndarray:
    """A noisy random RGB frame — phase correlation works best on
    textured images."""
    return rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)


# ─── Schema tests ─────────────────────────────────────────────────


def test_camera_state_defaults():
    cs = CameraState(frame=1)
    assert cs.x == 0.0
    assert cs.y == 0.0
    assert cs.zoom == 1.0
    assert cs.rotation == 0.0
    assert cs.confidence == 0.0


def test_camera_state_extra_field_forbidden():
    with pytest.raises(Exception):
        CameraState.model_validate({"frame": 1, "extra_field": 42})


def test_camera_state_negative_confidence_rejected():
    with pytest.raises(Exception):
        CameraState(frame=1, confidence=-0.1)


def test_camera_moves_map_round_trip():
    m = CameraMovesMap(
        shot_id="shot_001",
        frame_count=3,
        moves=[
            CameraState(frame=1, x=0, y=0, confidence=1.0),
            CameraState(frame=2, x=5, y=0, confidence=0.8),
            CameraState(frame=3, x=10, y=2, confidence=0.7),
        ],
    )
    serialized = m.model_dump_json()
    reloaded = CameraMovesMap.model_validate_json(serialized)
    assert reloaded.shot_id == "shot_001"
    assert len(reloaded.moves) == 3
    assert reloaded.moves[2].x == 10


# ─── _to_grayscale_float32 ────────────────────────────────────────


def test_to_grayscale_passes_through_existing_grayscale():
    frame = np.full((10, 10), 128.0, dtype=np.uint8)
    out = _to_grayscale_float32(frame)
    assert out.dtype == np.float32
    assert out.shape == (10, 10)
    assert (out == 128.0).all()


def test_to_grayscale_converts_rgb_with_luma():
    rgb = np.zeros((1, 1, 3), dtype=np.uint8)
    rgb[0, 0, 1] = 255  # pure green
    out = _to_grayscale_float32(rgb)
    # 0.587 * 255 ≈ 149.685
    assert out[0, 0] == pytest.approx(0.587 * 255, rel=0.01)


def test_to_grayscale_rejects_bad_shape():
    with pytest.raises(ValueError):
        _to_grayscale_float32(np.zeros((5,), dtype=np.uint8))


# ─── detect_translation ───────────────────────────────────────────


def test_detect_translation_no_shift():
    rng = np.random.default_rng(seed=42)
    frame = _random_frame(rng)
    dx, dy, conf = detect_translation(frame, frame)
    assert abs(dx) < 0.5
    assert abs(dy) < 0.5
    # Identical frames → high confidence
    assert conf > 0.1


def test_detect_translation_horizontal_pan():
    """Shift frame by +5 px horizontally; detector should recover ~5 px."""
    rng = np.random.default_rng(seed=7)
    frame_a = _random_frame(rng, h=128, w=128)
    frame_b = np.roll(frame_a, shift=5, axis=1)  # shift right by 5

    dx, dy, conf = detect_translation(frame_a, frame_b)
    # Sign convention depends on impl; test absolute magnitude
    assert abs(abs(dx) - 5.0) < 1.5, f"expected ~5 px horizontal shift, got dx={dx}"
    assert abs(dy) < 1.5, f"vertical shift should be ~0, got dy={dy}"
    assert conf > 0.05


def test_detect_translation_vertical_pan():
    rng = np.random.default_rng(seed=11)
    frame_a = _random_frame(rng)
    frame_b = np.roll(frame_a, shift=3, axis=0)  # shift down by 3

    dx, dy, conf = detect_translation(frame_a, frame_b)
    assert abs(dx) < 1.5
    assert abs(abs(dy) - 3.0) < 1.5


def test_detect_translation_diagonal_pan():
    rng = np.random.default_rng(seed=13)
    frame_a = _random_frame(rng)
    frame_b = np.roll(frame_a, shift=4, axis=0)
    frame_b = np.roll(frame_b, shift=-2, axis=1)

    dx, dy, _ = detect_translation(frame_a, frame_b)
    assert abs(abs(dx) - 2.0) < 1.5
    assert abs(abs(dy) - 4.0) < 1.5


def test_detect_translation_mismatched_shapes_raises():
    a = np.zeros((10, 10, 3), dtype=np.uint8)
    b = np.zeros((20, 20, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="shapes must match"):
        detect_translation(a, b)


# ─── numpy fallback ───────────────────────────────────────────────


def test_numpy_fallback_recovers_shift():
    """The pure-numpy fallback works (used when cv2 isn't available)."""
    rng = np.random.default_rng(seed=99)
    a = _random_frame(rng, h=64, w=64).astype(np.float32).mean(axis=2)
    b = np.roll(a, shift=7, axis=1)
    dx, dy, conf = _phase_correlate_numpy(a, b)
    assert abs(abs(dx) - 7.0) < 1.5
    assert abs(dy) < 1.5


# ─── load_frame ───────────────────────────────────────────────────


def test_load_frame_returns_rgb_array(tmp_path):
    from PIL import Image
    p = tmp_path / "test.png"
    Image.new("RGB", (16, 16), color=(255, 128, 0)).save(p)
    arr = load_frame(p)
    assert arr.shape == (16, 16, 3)
    assert arr[0, 0, 0] == 255  # R
    assert arr[0, 0, 1] == 128  # G
    assert arr[0, 0, 2] == 0    # B


# ─── detect_camera_moves_from_frames ──────────────────────────────


def _save_frame(path: Path, arr: np.ndarray) -> None:
    from PIL import Image
    Image.fromarray(arr).save(path, format="PNG")


def test_detect_camera_moves_static_frames(tmp_path):
    """Static frames → all CameraStates should be near (0, 0)."""
    rng = np.random.default_rng(seed=21)
    frame = _random_frame(rng)
    paths = []
    for i in range(5):
        p = tmp_path / f"frame_{i+1:04d}.png"
        _save_frame(p, frame)
        paths.append(p)

    moves = detect_camera_moves_from_frames(paths, shot_id="static")
    assert moves.shot_id == "static"
    assert moves.frame_count == 5
    assert len(moves.moves) == 5
    # Frame 1 is the anchor
    assert moves.moves[0].x == 0.0
    assert moves.moves[0].y == 0.0
    # Static frames → minimal cumulative drift
    final = moves.moves[-1]
    assert abs(final.x) < 2.0
    assert abs(final.y) < 2.0


def test_detect_camera_moves_horizontal_pan(tmp_path):
    """Frames panning right by 5 px per step → cumulative x grows."""
    rng = np.random.default_rng(seed=31)
    base = _random_frame(rng, h=128, w=128)
    paths = []
    for i in range(4):
        shifted = np.roll(base, shift=5 * i, axis=1)
        p = tmp_path / f"frame_{i+1:04d}.png"
        _save_frame(p, shifted)
        paths.append(p)

    moves = detect_camera_moves_from_frames(paths, shot_id="pan_right")
    # Frame 4 should have ~15 px cumulative shift (sign depends on convention)
    final = moves.moves[-1]
    assert abs(abs(final.x) - 15.0) < 3.0, f"expected ~±15 px, got {final.x}"


def test_detect_camera_moves_empty_input():
    moves = detect_camera_moves_from_frames([], shot_id="empty")
    assert moves.frame_count == 0
    assert moves.moves == []


def test_detect_camera_moves_single_frame(tmp_path):
    """A single input frame → exactly one CameraState (the anchor)."""
    from PIL import Image
    p = tmp_path / "frame_0001.png"
    Image.new("RGB", (32, 32), color=(100, 100, 100)).save(p)
    moves = detect_camera_moves_from_frames([p], shot_id="lone")
    assert moves.frame_count == 1
    assert len(moves.moves) == 1
    assert moves.moves[0].x == 0.0


def test_detect_camera_moves_low_confidence_zeroed(tmp_path):
    """A pair of unrelated random frames has low confidence; should
    be treated as zero-movement."""
    rng = np.random.default_rng(seed=51)
    a = _random_frame(rng)
    b = _random_frame(np.random.default_rng(seed=52))  # totally different
    pa = tmp_path / "frame_0001.png"
    pb = tmp_path / "frame_0002.png"
    _save_frame(pa, a)
    _save_frame(pb, b)
    # Set a very HIGH confidence floor so the detection is zeroed
    moves = detect_camera_moves_from_frames(
        [pa, pb], shot_id="unrelated", confidence_floor=0.99,
    )
    assert moves.moves[1].x == 0.0
    assert moves.moves[1].y == 0.0


# ─── CLI tests ────────────────────────────────────────────────────


def test_cli_writes_camera_moves_json(tmp_path):
    from animate_cc_pipeline.pipeline.cli_camera_detector import main as cli_main

    rng = np.random.default_rng(seed=71)
    frame = _random_frame(rng)
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    for i in range(3):
        _save_frame(frames_dir / f"frame_{i+1:04d}.png", frame)

    out_json = tmp_path / "moves.json"
    rc = cli_main([
        "--frames-dir", str(frames_dir),
        "--shot-id", "test_shot",
        "--out", str(out_json),
        "--log-level", "ERROR",
    ])
    assert rc == 0
    assert out_json.exists()
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["shot_id"] == "test_shot"
    assert data["frame_count"] == 3
    assert len(data["moves"]) == 3


def test_cli_fails_on_missing_frames_dir(tmp_path):
    from animate_cc_pipeline.pipeline.cli_camera_detector import main as cli_main

    rc = cli_main([
        "--frames-dir", str(tmp_path / "no_such_dir"),
        "--shot-id", "x",
        "--out", str(tmp_path / "out.json"),
        "--log-level", "ERROR",
    ])
    assert rc == 2


def test_cli_fails_on_empty_frames_dir(tmp_path):
    from animate_cc_pipeline.pipeline.cli_camera_detector import main as cli_main

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    rc = cli_main([
        "--frames-dir", str(empty_dir),
        "--shot-id", "x",
        "--out", str(tmp_path / "out.json"),
        "--log-level", "ERROR",
    ])
    assert rc == 2
