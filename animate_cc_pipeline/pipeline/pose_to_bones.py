"""Pose → bone angle / rig position / rig scale math.

Phase 3k: pure-Python module that translates Node 6's joint
coordinates into the inputs the orchestrator feeds to MCP tools.

Conventions:
  - Coordinates are in Animate stage pixels: x right, y DOWN.
  - Bone angles are in DEGREES, computed via atan2(dy, dx). So a
    bone pointing right is 0°, pointing down is +90°, pointing left
    is +180° (or -180°), pointing up is -90°.
  - Returns None for any computation that needs a joint that's
    missing or low-confidence; consumers (orchestrator) handle this
    by interpolating from the last reliable frame.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, degrees, hypot
from typing import Optional

from .schemas import Joint, JointSet


# ─── Rig spec dataclass ───────────────────────────────────────────


@dataclass
class RigSpec:
    """Subset of a rig's `_metadata` JSON used by the math here.

    The orchestrator reads the full _metadata via the
    `dump_rig_structure` JSFL helper (Phase 3f) and constructs a
    RigSpec from it.
    """

    identity: str
    default_height_units: float
    default_shoulder_width_units: float
    head_pivot_offset: tuple[float, float]
    """Offset from the rig's origin (0,0) to the head joint in the
    rig's default coordinate space. Used to anchor the rig to a
    pose's nose joint."""
    feet_pivot_offset: tuple[float, float] = (0.0, 0.0)
    rotation_strip_angle_step: int = 45
    """Degrees between consecutive rotation strip frames (default 8
    frames at 45° = 0, 45, 90, ..., 315)."""
    rotation_strip_frame_count: int = 8


# ─── Bone → joint mapping ─────────────────────────────────────────


# Each entry: (parent_joint_attr, child_joint_attr) on JointSet.
# Bone angle is computed from the vector parent → child.
BONE_TO_JOINTS: dict[str, tuple[str, str]] = {
    "bone_head":          ("neck",       "nose"),
    "bone_arm_L_upper":   ("shoulder_L", "elbow_L"),
    "bone_arm_L_lower":   ("elbow_L",    "wrist_L"),
    "bone_arm_R_upper":   ("shoulder_R", "elbow_R"),
    "bone_arm_R_lower":   ("elbow_R",    "wrist_R"),
    "bone_leg_L_upper":   ("hip_L",      "knee_L"),
    "bone_leg_L_lower":   ("knee_L",     "ankle_L"),
    "bone_leg_R_upper":   ("hip_R",      "knee_R"),
    "bone_leg_R_lower":   ("knee_R",     "ankle_R"),
}


# ─── Public API ───────────────────────────────────────────────────


def compute_bone_angle(parent: Optional[Joint], child: Optional[Joint]) -> Optional[float]:
    """Angle of bone from parent to child, in degrees.

    Animate stage convention: x right, y DOWN. atan2(dy, dx) gives:
      - 0°    = bone points right
      - +90°  = bone points down
      - ±180° = bone points left
      - -90°  = bone points up

    Returns None if either joint is None.
    """
    if parent is None or child is None:
        return None
    dx = child.x - parent.x
    dy = child.y - parent.y
    return degrees(atan2(dy, dx))


def compute_bone_angles_from_pose(
    pose: JointSet,
    rig_spec: RigSpec | None = None,
) -> dict[str, Optional[float]]:
    """Compute angle for each rig bone given pose joints.

    Returns a dict mapping bone path -> angle in degrees, with None
    for any bone whose joints are missing.

    `rig_spec` is currently unused for angle computation (the math
    is rig-agnostic) but kept in the signature for future extension
    (e.g., per-rig angle reference offsets).
    """
    out: dict[str, Optional[float]] = {}
    for bone_path, (parent_attr, child_attr) in BONE_TO_JOINTS.items():
        parent_joint: Optional[Joint] = getattr(pose, parent_attr, None)
        child_joint: Optional[Joint] = getattr(pose, child_attr, None)
        out[bone_path] = compute_bone_angle(parent_joint, child_joint)
    return out


def angle_to_rotation_strip_frame(
    angle_degrees: float,
    frame_count: int = 8,
    angle_step: int = 45,
) -> int:
    """Map a continuous bone angle to a discrete rotation strip frame index.

    The strip is assumed to be organized at uniform `angle_step`°
    intervals starting at 0° (frame 0 = bone pointing right in
    Animate stage convention).

    Wraps around at 360°. Returns int in [0, frame_count).

    Examples (frame_count=8, angle_step=45):
        0°   → 0
        45°  → 1
        90°  → 2
        180° → 4
        360° → 0 (wraps)
        -45° → 7 (equivalent to 315°)
    """
    if frame_count <= 0:
        raise ValueError(f"frame_count must be positive, got {frame_count}")
    if angle_step <= 0:
        raise ValueError(f"angle_step must be positive, got {angle_step}")
    # Normalize to [0, 360)
    normalized = angle_degrees % 360.0
    # Round to nearest frame
    frame = int(round(normalized / angle_step)) % frame_count
    return frame


def compute_rig_position(
    pose: JointSet,
    rig_spec: RigSpec,
) -> Optional[tuple[float, float]]:
    """Compute canvas position to place the rig so its head aligns
    with the pose's nose joint.

    Math: canvas_origin = nose_position - head_pivot_offset.
    (The rig's origin is at its feet by default; head_pivot_offset
    is the head position relative to that origin.)

    Returns None if pose has no nose joint.
    """
    if pose.nose is None:
        return None
    px = pose.nose.x - rig_spec.head_pivot_offset[0]
    py = pose.nose.y - rig_spec.head_pivot_offset[1]
    return (px, py)


def compute_rig_scale(
    pose: JointSet,
    rig_spec: RigSpec,
) -> Optional[float]:
    """Compute rig scale so the rig's shoulders match the pose's
    shoulder width.

    Shoulder width is pose-invariant (it doesn't shrink when the
    character sits or crouches the way bbox height does), making
    it the right anchor for size matching.

    Returns None if either shoulder joint is None or if the rig's
    default shoulder width is invalid.
    """
    if pose.shoulder_L is None or pose.shoulder_R is None:
        return None
    if rig_spec.default_shoulder_width_units <= 0:
        return None
    pose_width = hypot(
        pose.shoulder_R.x - pose.shoulder_L.x,
        pose.shoulder_R.y - pose.shoulder_L.y,
    )
    return pose_width / rig_spec.default_shoulder_width_units


def bone_angles_to_strip_frames(
    bone_angles: dict[str, Optional[float]],
    rig_spec: RigSpec,
) -> dict[str, Optional[int]]:
    """Convenience: convert a bone-angle dict to a rotation-strip
    frame-index dict using the rig's strip parameters.

    Bones whose angle is None get a None entry. The orchestrator
    skips those bones (interpolates from a prior frame or leaves
    the rig at default).
    """
    out: dict[str, Optional[int]] = {}
    for bone, angle in bone_angles.items():
        if angle is None:
            out[bone] = None
        else:
            out[bone] = angle_to_rotation_strip_frame(
                angle,
                frame_count=rig_spec.rotation_strip_frame_count,
                angle_step=rig_spec.rotation_strip_angle_step,
            )
    return out


# ─── Convenience: load a RigSpec from a dict (e.g. _metadata JSON) ─


def rig_spec_from_metadata(metadata: dict) -> RigSpec:
    """Construct a RigSpec from a rig's `_metadata` JSON dict.

    Tolerant of extra fields (for forward-compat) and missing
    optional fields (uses defaults).
    """
    head_offset = metadata.get("head_pivot_offset", [0, 0])
    feet_offset = metadata.get("feet_pivot_offset", [0, 0])
    if not (isinstance(head_offset, (list, tuple)) and len(head_offset) >= 2):
        head_offset = [0, 0]
    if not (isinstance(feet_offset, (list, tuple)) and len(feet_offset) >= 2):
        feet_offset = [0, 0]

    return RigSpec(
        identity=str(metadata.get("identity", "")),
        default_height_units=float(metadata.get("default_height_units", 600)),
        default_shoulder_width_units=float(
            metadata.get("default_shoulder_width_units", 250)
        ),
        head_pivot_offset=(float(head_offset[0]), float(head_offset[1])),
        feet_pivot_offset=(float(feet_offset[0]), float(feet_offset[1])),
        rotation_strip_angle_step=int(metadata.get("rotation_strip_angle_step", 45)),
        rotation_strip_frame_count=int(metadata.get("rotation_strip_frame_count", 8)),
    )
