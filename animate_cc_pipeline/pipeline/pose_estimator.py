"""Pose-estimator interface and factory.

Backends implement a single method: given an image array + a bbox,
return a `JointSet`. Backends can be swapped via CLI flag.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from .schemas import Bbox, JointSet


@runtime_checkable
class PoseEstimator(Protocol):
    """All pose backends implement this Protocol."""

    name: str
    """Backend identifier (e.g. 'mock', 'http', 'dwpose_local').
    Stored in node6_result.json's `backend` field for provenance."""

    def estimate_pose(self, image: np.ndarray, bbox: Bbox) -> JointSet:
        """Estimate joints for one character on one frame.

        Args:
            image: the FULL frame as an HxWx3 numpy array (RGB).
            bbox: the character's bounding box. The implementation
                  may crop internally or pass the full frame to its
                  model along with the bbox.

        Returns:
            A JointSet. Joints below the backend's confidence
            threshold should be set to None (consumer handles).
        """
        ...


def get_pose_estimator(backend: str, **kwargs) -> PoseEstimator:
    """Factory: returns a PoseEstimator instance for the named backend.

    Supported backends:
      - 'mock'  — deterministic synthetic poses (default for testing)
      - 'http'  — HTTP POST to a remote service; kwargs['url'] required
      - 'dwpose_local' — local DWPose; deferred, raises ImportError
                         if optional deps not installed
    """
    if backend == "mock":
        from .pose_backends.mock import MockPoseEstimator
        return MockPoseEstimator()
    elif backend == "http":
        from .pose_backends.http_client import HttpPoseEstimator
        url = kwargs.get("url")
        if not url:
            raise ValueError("backend='http' requires kwarg url='...'")
        timeout = kwargs.get("timeout", 30)
        return HttpPoseEstimator(url=url, timeout=timeout)
    elif backend == "dwpose_local":
        try:
            from .pose_backends.dwpose_local import DwposeLocalEstimator
        except ImportError as exc:
            raise ImportError(
                "backend='dwpose_local' requires optional deps: "
                "torch, onnxruntime, plus DWPose weights. Install via "
                "the operator-side instructions in docs/PHASE_3_ROADMAP.md "
                "Phase 3j section. Original error: "
                f"{exc}"
            ) from exc
        return DwposeLocalEstimator()
    else:
        raise ValueError(
            f"unknown backend {backend!r}; must be one of "
            "'mock', 'http', 'dwpose_local'"
        )
