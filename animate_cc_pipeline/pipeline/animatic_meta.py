"""ffprobe-based animatic metadata extraction (Phase 3p-fixup-1).

Adobe Animate 2020's `doc.importFile(<mp4>, false)` ALWAYS pops up
the modal "Import Video" wizard, which JSFL cannot dismiss. So the
pipeline cannot embed rough animatic MP4s into the .fla directly.

Workaround: use ffprobe (Python-side, via imageio-ffmpeg) to read
the animatic's duration + frame count, and extend the .fla's
timeline programmatically to match. The animator references the
rough externally (separate video player) during the touch-up pass.

Documented as JSFL Gotcha #16 in CLAUDE.md.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


logger = logging.getLogger("animatic_meta")


@dataclass
class AnimaticMeta:
    """Minimal metadata extracted from a rough animatic MP4."""
    duration_seconds: float
    width: int
    height: int
    fps: float

    def frame_count_at(self, target_fps: int) -> int:
        """Frame count required to cover the animatic's duration at
        `target_fps`. Rounded up (so the rendered MP4 is at least
        as long as the rough)."""
        return max(1, int(round(self.duration_seconds * target_fps)))


def _ffprobe_path() -> Optional[Path]:
    """Locate ffprobe.exe shipped alongside imageio-ffmpeg's ffmpeg.

    imageio-ffmpeg only ships ffmpeg.exe, not ffprobe — but ffmpeg
    itself can probe via `-i <file>` and parse the stderr. We use
    that fallback when ffprobe isn't installed.
    """
    try:
        import imageio_ffmpeg
        ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
    except ImportError:
        return None
    # ffprobe might be in the same directory as ffmpeg
    candidate = ffmpeg.parent / "ffprobe.exe"
    if candidate.exists():
        return candidate
    # Some installs name it differently
    candidate = Path(str(ffmpeg).replace("ffmpeg", "ffprobe"))
    if candidate.exists() and candidate != ffmpeg:
        return candidate
    return None


def _ffmpeg_path() -> Optional[Path]:
    try:
        import imageio_ffmpeg
        return Path(imageio_ffmpeg.get_ffmpeg_exe())
    except ImportError:
        return None


def probe_animatic(mp4_path: Path) -> Optional[AnimaticMeta]:
    """Read duration + dimensions + fps from a rough animatic MP4.

    Uses ffprobe if available (preferred — emits JSON), else parses
    ffmpeg's stderr output. Returns None on any failure.
    """
    if not mp4_path.exists():
        logger.warning("animatic not found: %s", mp4_path)
        return None

    ffprobe = _ffprobe_path()
    if ffprobe is not None:
        return _probe_via_ffprobe(mp4_path, ffprobe)

    ffmpeg = _ffmpeg_path()
    if ffmpeg is not None:
        return _probe_via_ffmpeg_stderr(mp4_path, ffmpeg)

    logger.warning("no ffprobe or ffmpeg available to probe %s", mp4_path)
    return None


def _probe_via_ffprobe(mp4_path: Path, ffprobe: Path) -> Optional[AnimaticMeta]:
    cmd = [
        str(ffprobe), "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,duration:format=duration",
        "-of", "json",
        str(mp4_path),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, check=True
        )
        data = json.loads(result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            json.JSONDecodeError) as exc:
        logger.warning("ffprobe failed for %s: %s", mp4_path, exc)
        return None

    streams = data.get("streams", [])
    fmt = data.get("format", {})
    if not streams:
        return None
    s = streams[0]
    width = int(s.get("width", 0))
    height = int(s.get("height", 0))

    # r_frame_rate is "num/den" (e.g., "25/1")
    fps_str = s.get("r_frame_rate", "25/1")
    if "/" in fps_str:
        num, den = fps_str.split("/")
        try:
            fps = float(num) / float(den) if float(den) != 0 else 25.0
        except ValueError:
            fps = 25.0
    else:
        try:
            fps = float(fps_str)
        except ValueError:
            fps = 25.0

    # Duration: try stream first, fall back to format
    duration = s.get("duration") or fmt.get("duration")
    try:
        duration_s = float(duration) if duration is not None else 0.0
    except (TypeError, ValueError):
        duration_s = 0.0

    if duration_s <= 0:
        return None

    return AnimaticMeta(
        duration_seconds=duration_s,
        width=width or 1920,
        height=height or 1080,
        fps=fps,
    )


def _probe_via_ffmpeg_stderr(mp4_path: Path, ffmpeg: Path) -> Optional[AnimaticMeta]:
    """Fallback: parse `ffmpeg -i <file>` stderr.

    `imageio-ffmpeg` only ships ffmpeg.exe (not ffprobe). When fed
    just `-i <file>`, ffmpeg dumps the container/stream info to
    stderr and exits with a non-zero code (because no output file
    was specified). We parse the duration and stream lines.
    """
    cmd = [str(ffmpeg), "-i", str(mp4_path)]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning("ffmpeg probe timed out for %s: %s", mp4_path, exc)
        return None

    stderr = result.stderr
    duration_s = _parse_duration_from_ffmpeg_stderr(stderr)
    width, height, fps = _parse_video_stream_from_ffmpeg_stderr(stderr)
    if duration_s is None:
        return None
    return AnimaticMeta(
        duration_seconds=duration_s,
        width=width or 1920,
        height=height or 1080,
        fps=fps or 25.0,
    )


def _parse_duration_from_ffmpeg_stderr(stderr: str) -> Optional[float]:
    """Find a line like `  Duration: 00:00:00.92, start: 0.000000, ...`"""
    import re
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if not m:
        return None
    hh, mm, ss = m.groups()
    try:
        return int(hh) * 3600 + int(mm) * 60 + float(ss)
    except ValueError:
        return None


def _parse_video_stream_from_ffmpeg_stderr(
    stderr: str,
) -> tuple[Optional[int], Optional[int], Optional[float]]:
    """Find dimensions + fps from a 'Stream #0:0: Video' line."""
    import re
    width = height = fps = None
    for line in stderr.splitlines():
        if "Video:" not in line:
            continue
        m = re.search(r"(\d{3,5})x(\d{3,5})", line)
        if m:
            width = int(m.group(1))
            height = int(m.group(2))
        m = re.search(r"(\d+(?:\.\d+)?)\s*fps", line)
        if m:
            try:
                fps = float(m.group(1))
            except ValueError:
                pass
        break
    return (width, height, fps)
