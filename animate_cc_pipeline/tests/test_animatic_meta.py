"""Unit tests for pipeline.animatic_meta (Phase 3p-fixup-1)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from animate_cc_pipeline.pipeline import animatic_meta


# ─── AnimaticMeta dataclass ──────────────────────────────────────


def test_animatic_meta_frame_count_at_round():
    """frame_count_at rounds the duration*fps product."""
    m = animatic_meta.AnimaticMeta(
        duration_seconds=0.88, width=1280, height=720, fps=25.0,
    )
    assert m.frame_count_at(25) == 22
    assert m.frame_count_at(30) == 26
    assert m.frame_count_at(60) == 53  # 0.88 * 60 = 52.8 -> 53


def test_animatic_meta_frame_count_minimum_one():
    """A near-zero duration still maps to at least one frame."""
    m = animatic_meta.AnimaticMeta(
        duration_seconds=0.0001, width=1, height=1, fps=25.0,
    )
    assert m.frame_count_at(25) == 1


# ─── _parse_duration_from_ffmpeg_stderr ─────────────────────────


def test_parse_duration_from_stderr():
    """Real ffmpeg stderr format: 'Duration: 00:00:00.88, ...'"""
    stderr = "  Duration: 00:00:00.88, start: 0.000000, bitrate: 2400 kb/s"
    assert animatic_meta._parse_duration_from_ffmpeg_stderr(stderr) == pytest.approx(0.88, abs=0.01)


def test_parse_duration_hours_minutes_seconds():
    stderr = "  Duration: 01:23:45.50, start: 0.000000"
    assert animatic_meta._parse_duration_from_ffmpeg_stderr(stderr) == pytest.approx(
        1 * 3600 + 23 * 60 + 45.5, abs=0.01,
    )


def test_parse_duration_missing_returns_none():
    assert animatic_meta._parse_duration_from_ffmpeg_stderr("no duration here") is None


# ─── _parse_video_stream_from_ffmpeg_stderr ─────────────────────


def test_parse_video_stream_dims_and_fps():
    stderr = (
        "Stream #0:0(und): Video: h264 (High) (avc1 / 0x31637661), "
        "yuv420p(progressive), 1920x1080, 172 kb/s, 25 fps, 25 tbr, 12800 tbn"
    )
    w, h, fps = animatic_meta._parse_video_stream_from_ffmpeg_stderr(stderr)
    assert w == 1920
    assert h == 1080
    assert fps == pytest.approx(25.0)


def test_parse_video_stream_fractional_fps():
    stderr = "Stream #0:0: Video: h264, 1280x720, 23.98 fps, 24 tbr"
    w, h, fps = animatic_meta._parse_video_stream_from_ffmpeg_stderr(stderr)
    assert w == 1280
    assert h == 720
    assert fps == pytest.approx(23.98)


def test_parse_video_stream_no_match():
    w, h, fps = animatic_meta._parse_video_stream_from_ffmpeg_stderr("nothing here")
    assert (w, h, fps) == (None, None, None)


# ─── probe_animatic ──────────────────────────────────────────────


def test_probe_animatic_missing_file(tmp_path):
    """Non-existent file → None, no exception."""
    assert animatic_meta.probe_animatic(tmp_path / "no_such.mp4") is None


def test_probe_animatic_on_real_demo_mp4():
    """Smoke: ffprobe should work on the demo MP4 we already produced.

    This validates the full path through either ffprobe or
    the ffmpeg-stderr fallback against an actual MP4 we control.
    """
    demo_mp4 = REPO_ROOT / "work" / "phase3p_demo" / "jethalal_demo.mp4"
    if not demo_mp4.exists():
        pytest.skip("phase3p_demo MP4 not produced yet (run smoke first)")
    meta = animatic_meta.probe_animatic(demo_mp4)
    assert meta is not None, "probe_animatic should succeed on the demo MP4"
    assert meta.width == 1920
    assert meta.height == 1080
    assert meta.duration_seconds > 0
    # Demo is 1 frame @ 25fps = 0.04s
    assert meta.frame_count_at(25) >= 1
