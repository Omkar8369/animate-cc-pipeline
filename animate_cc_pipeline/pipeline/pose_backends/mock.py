"""Mock pose backend — deterministic synthetic joints from bbox.

For testing the pipeline shape without needing a real pose model.
Useful as the orchestrator's default during development.

The synthetic poses are roughly anatomically plausible:
  - head joints near bbox top
  - shoulders just below the top quarter
  - hands extend horizontally from the bbox center
  - legs extend down to bbox bottom

All confidences are 0.9 (deterministic; no noise).
"""

from __future__ import annotations

import numpy as np

from ..schemas import Bbox, Joint, JointSet


class MockPoseEstimator:
    name = "mock"

    def estimate_pose(self, image: np.ndarray, bbox: Bbox) -> JointSet:
        """Return synthetic joints based on bbox geometry alone.

        `image` argument is ignored — this backend has no model.
        """
        x, y, w, h = bbox.x, bbox.y, bbox.w, bbox.h
        cx = x + w / 2
        cy_top = y + h * 0.08          # head height
        cy_neck = y + h * 0.18
        cy_shoulder = y + h * 0.22
        cy_elbow = y + h * 0.40
        cy_wrist = y + h * 0.55
        cy_hip = y + h * 0.55
        cy_knee = y + h * 0.78
        cy_ankle = y + h - 1

        sw = w * 0.22  # shoulder half-width
        hw = w * 0.18  # hip half-width

        def j(jx: float, jy: float, conf: float = 0.9) -> Joint:
            return Joint(x=float(jx), y=float(jy), confidence=conf)

        return JointSet(
            nose=j(cx, cy_top),
            neck=j(cx, cy_neck),
            shoulder_L=j(cx - sw, cy_shoulder),
            shoulder_R=j(cx + sw, cy_shoulder),
            elbow_L=j(cx - sw - w * 0.05, cy_elbow),
            elbow_R=j(cx + sw + w * 0.05, cy_elbow),
            wrist_L=j(cx - sw - w * 0.08, cy_wrist),
            wrist_R=j(cx + sw + w * 0.08, cy_wrist),
            hip_L=j(cx - hw, cy_hip),
            hip_R=j(cx + hw, cy_hip),
            knee_L=j(cx - hw, cy_knee),
            knee_R=j(cx + hw, cy_knee),
            ankle_L=j(cx - hw, cy_ankle),
            ankle_R=j(cx + hw, cy_ankle),
        )
