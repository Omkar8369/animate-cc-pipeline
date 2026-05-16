"""HTTP pose-estimation backend.

POSTs the full frame as a PNG + the bbox as JSON to a remote pose
service. The intended deployment is a small FastAPI app on a RunPod
GPU box that wraps DWPose (or similar).

HTTP contract: see docs/PHASE_3_ROADMAP.md Phase 3j section.

Network failures are RAISED, not silently swallowed — the CLI is
responsible for catching + logging per-character soft failures.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from typing import Any

import numpy as np

from ..errors import PoseBackendError
from ..schemas import Bbox, Joint, JointSet, JOINT_NAMES


class HttpPoseEstimator:
    name = "http"

    def __init__(self, url: str, timeout: int = 30):
        self.url = url.rstrip("/")
        self.timeout = timeout

    def estimate_pose(self, image: np.ndarray, bbox: Bbox) -> JointSet:
        try:
            import imageio.v3 as iio
        except ImportError:
            try:
                import imageio as iio  # type: ignore
            except ImportError as exc:
                raise PoseBackendError(
                    "HTTP backend requires imageio (or PIL) to encode "
                    "frames to PNG. Install via "
                    "`pip install imageio` (typically already present "
                    "as a transitive dep)."
                ) from exc

        # Encode the image array to PNG bytes
        png_buf = io.BytesIO()
        try:
            iio.imwrite(png_buf, image, extension=".png")
        except TypeError:
            # Older imageio API
            iio.imwrite(png_buf, image, format="png")  # type: ignore

        png_bytes = png_buf.getvalue()

        # Multipart-encode the request body manually (no external deps)
        boundary = "----animatecc-bridge-7Tq9aF"
        bbox_json = json.dumps({"x": bbox.x, "y": bbox.y, "w": bbox.w, "h": bbox.h}).encode("utf-8")

        body = b""
        body += f"--{boundary}\r\n".encode("utf-8")
        body += b'Content-Disposition: form-data; name="bbox"\r\n\r\n'
        body += bbox_json + b"\r\n"
        body += f"--{boundary}\r\n".encode("utf-8")
        body += b'Content-Disposition: form-data; name="image_frame"; filename="frame.png"\r\n'
        body += b"Content-Type: image/png\r\n\r\n"
        body += png_bytes + b"\r\n"
        body += f"--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(
            f"{self.url}/estimate_pose",
            data=body,
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise PoseBackendError(
                f"HTTP pose service unreachable at {self.url}: {exc}"
            ) from exc

        return _decode_joints_payload(payload.get("joints", {}))


def _decode_joints_payload(payload: dict[str, Any]) -> JointSet:
    """Convert a `{joint_name: {x, y, confidence}}` payload into a JointSet."""
    fields: dict[str, Joint | None] = {}
    for name in JOINT_NAMES:
        entry = payload.get(name)
        if not entry:
            fields[name] = None
            continue
        try:
            fields[name] = Joint(
                x=float(entry["x"]),
                y=float(entry["y"]),
                confidence=float(entry.get("confidence", 0.0)),
            )
        except (KeyError, ValueError, TypeError):
            fields[name] = None
    return JointSet(**fields)
