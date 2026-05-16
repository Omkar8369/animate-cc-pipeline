"""Unit tests for pose-to-bone angle math.

Pure-Python tests. Verifies the math on synthetic joint coordinates
with known geometries.
"""

from __future__ import annotations

import math

import pytest

from animate_cc_pipeline.pipeline.pose_to_bones import (
    BONE_TO_JOINTS,
    RigSpec,
    angle_to_rotation_strip_frame,
    bone_angles_to_strip_frames,
    compute_bone_angle,
    compute_bone_angles_from_pose,
    compute_rig_position,
    compute_rig_scale,
    rig_spec_from_metadata,
)
from animate_cc_pipeline.pipeline.schemas import Joint, JointSet


# ─── Helpers ──────────────────────────────────────────────────────


def _j(x: float, y: float, c: float = 0.9) -> Joint:
    return Joint(x=x, y=y, confidence=c)


def _default_rig() -> RigSpec:
    return RigSpec(
        identity="TEST",
        default_height_units=600,
        default_shoulder_width_units=200,
        head_pivot_offset=(0, -540),
        feet_pivot_offset=(0, 0),
        rotation_strip_angle_step=45,
        rotation_strip_frame_count=8,
    )


# ─── compute_bone_angle ───────────────────────────────────────────


def test_bone_angle_horizontal_right():
    parent = _j(100, 100)
    child = _j(200, 100)  # to the right
    assert compute_bone_angle(parent, child) == pytest.approx(0.0)


def test_bone_angle_vertical_down():
    parent = _j(100, 100)
    child = _j(100, 200)  # below in Animate (y grows down)
    assert compute_bone_angle(parent, child) == pytest.approx(90.0)


def test_bone_angle_vertical_up():
    parent = _j(100, 200)
    child = _j(100, 100)  # above
    assert compute_bone_angle(parent, child) == pytest.approx(-90.0)


def test_bone_angle_horizontal_left():
    parent = _j(100, 100)
    child = _j(0, 100)  # to the left
    assert abs(compute_bone_angle(parent, child)) == pytest.approx(180.0)


def test_bone_angle_diagonal_down_right_45():
    parent = _j(0, 0)
    child = _j(100, 100)  # down + right
    assert compute_bone_angle(parent, child) == pytest.approx(45.0)


def test_bone_angle_diagonal_up_left():
    parent = _j(100, 100)
    child = _j(0, 0)  # up + left
    assert compute_bone_angle(parent, child) == pytest.approx(-135.0)


def test_bone_angle_returns_none_when_parent_missing():
    assert compute_bone_angle(None, _j(0, 0)) is None


def test_bone_angle_returns_none_when_child_missing():
    assert compute_bone_angle(_j(0, 0), None) is None


def test_bone_angle_returns_none_when_both_missing():
    assert compute_bone_angle(None, None) is None


# ─── compute_bone_angles_from_pose ────────────────────────────────


def test_full_pose_yields_all_arm_and_leg_bones():
    pose = JointSet(
        nose=_j(100, 50),
        neck=_j(100, 100),
        shoulder_L=_j(80, 110),
        shoulder_R=_j(120, 110),
        elbow_L=_j(60, 160),    # left arm hanging down-left from shoulder
        elbow_R=_j(140, 160),
        wrist_L=_j(50, 210),
        wrist_R=_j(150, 210),
        hip_L=_j(85, 250),
        hip_R=_j(115, 250),
        knee_L=_j(85, 350),
        knee_R=_j(115, 350),
        ankle_L=_j(85, 450),
        ankle_R=_j(115, 450),
    )
    angles = compute_bone_angles_from_pose(pose, _default_rig())
    # All bones in BONE_TO_JOINTS should have an entry
    for bone in BONE_TO_JOINTS:
        assert bone in angles
        assert angles[bone] is not None, f"bone {bone} should have an angle"


def test_legs_straight_down_are_90_degrees():
    pose = JointSet(
        hip_L=_j(100, 200),
        knee_L=_j(100, 300),
        ankle_L=_j(100, 400),
        hip_R=_j(150, 200),
        knee_R=_j(150, 300),
        ankle_R=_j(150, 400),
    )
    angles = compute_bone_angles_from_pose(pose, _default_rig())
    assert angles["bone_leg_L_upper"] == pytest.approx(90.0)
    assert angles["bone_leg_L_lower"] == pytest.approx(90.0)
    assert angles["bone_leg_R_upper"] == pytest.approx(90.0)
    assert angles["bone_leg_R_lower"] == pytest.approx(90.0)


def test_arm_raised_overhead_is_negative_90():
    """Arm shoulder→elbow pointing UP from shoulder (overhead) = -90°."""
    pose = JointSet(
        shoulder_L=_j(100, 200),
        elbow_L=_j(100, 100),   # directly above shoulder
        wrist_L=_j(100, 50),    # even higher
    )
    angles = compute_bone_angles_from_pose(pose, _default_rig())
    assert angles["bone_arm_L_upper"] == pytest.approx(-90.0)
    assert angles["bone_arm_L_lower"] == pytest.approx(-90.0)


def test_missing_joints_yield_none():
    pose = JointSet(
        nose=_j(100, 50),
        # neck missing
        shoulder_L=_j(80, 110),
        # elbow_L missing
    )
    angles = compute_bone_angles_from_pose(pose, _default_rig())
    assert angles["bone_head"] is None       # neck missing
    assert angles["bone_arm_L_upper"] is None  # elbow_L missing


# ─── angle_to_rotation_strip_frame ───────────────────────────────


def test_strip_frame_zero_degrees():
    assert angle_to_rotation_strip_frame(0) == 0


def test_strip_frame_45_degrees():
    assert angle_to_rotation_strip_frame(45) == 1


def test_strip_frame_90_degrees():
    assert angle_to_rotation_strip_frame(90) == 2


def test_strip_frame_180_degrees():
    assert angle_to_rotation_strip_frame(180) == 4


def test_strip_frame_wraps_at_360():
    assert angle_to_rotation_strip_frame(360) == 0


def test_strip_frame_handles_negative_angles():
    # -45° == 315°  →  frame 7
    assert angle_to_rotation_strip_frame(-45) == 7


def test_strip_frame_rounds_to_nearest():
    # 22° is between 0° and 45°, closer to 0°
    assert angle_to_rotation_strip_frame(22) == 0
    # 23° rounds to 45° = frame 1
    assert angle_to_rotation_strip_frame(23) == 1
    # 67° rounds to 45° = frame 1 (67 < 67.5)
    assert angle_to_rotation_strip_frame(67) == 1
    # 68° rounds to 90° = frame 2
    assert angle_to_rotation_strip_frame(68) == 2


def test_strip_frame_alternative_step():
    """If a rig uses 12 frames at 30° each, 90° → frame 3."""
    assert angle_to_rotation_strip_frame(90, frame_count=12, angle_step=30) == 3


def test_strip_frame_invalid_params_raise():
    with pytest.raises(ValueError):
        angle_to_rotation_strip_frame(0, frame_count=0)
    with pytest.raises(ValueError):
        angle_to_rotation_strip_frame(0, angle_step=0)


# ─── compute_rig_position ─────────────────────────────────────────


def test_rig_position_anchors_to_nose():
    pose = JointSet(nose=_j(500, 300))
    rig = RigSpec(
        identity="X",
        default_height_units=600,
        default_shoulder_width_units=200,
        head_pivot_offset=(0, -540),
    )
    pos = compute_rig_position(pose, rig)
    assert pos is not None
    # canvas_x = 500 - 0 = 500
    # canvas_y = 300 - (-540) = 840
    assert pos == (500.0, 840.0)


def test_rig_position_with_offset_head_pivot():
    pose = JointSet(nose=_j(0, 0))
    rig = RigSpec(
        identity="X",
        default_height_units=600,
        default_shoulder_width_units=200,
        head_pivot_offset=(10, 20),
    )
    pos = compute_rig_position(pose, rig)
    assert pos == (-10.0, -20.0)


def test_rig_position_returns_none_without_nose():
    pose = JointSet()  # no nose
    assert compute_rig_position(pose, _default_rig()) is None


# ─── compute_rig_scale ────────────────────────────────────────────


def test_rig_scale_unit_when_pose_matches_default():
    pose = JointSet(
        shoulder_L=_j(0, 0),
        shoulder_R=_j(200, 0),
    )
    rig = RigSpec(
        identity="X",
        default_height_units=600,
        default_shoulder_width_units=200,
        head_pivot_offset=(0, 0),
    )
    assert compute_rig_scale(pose, rig) == pytest.approx(1.0)


def test_rig_scale_half_when_pose_shoulders_half_width():
    pose = JointSet(
        shoulder_L=_j(0, 0),
        shoulder_R=_j(100, 0),  # half the rig's default 200
    )
    rig = _default_rig()
    assert compute_rig_scale(pose, rig) == pytest.approx(0.5)


def test_rig_scale_double_when_pose_shoulders_doubled():
    pose = JointSet(
        shoulder_L=_j(0, 0),
        shoulder_R=_j(400, 0),
    )
    rig = _default_rig()
    assert compute_rig_scale(pose, rig) == pytest.approx(2.0)


def test_rig_scale_uses_euclidean_distance():
    """Shoulder width is hypot — works for diagonal shoulders too."""
    pose = JointSet(
        shoulder_L=_j(0, 0),
        shoulder_R=_j(120, 160),  # hypot = 200
    )
    rig = _default_rig()  # default shoulder width = 200
    assert compute_rig_scale(pose, rig) == pytest.approx(1.0)


def test_rig_scale_returns_none_when_shoulder_missing():
    pose = JointSet(shoulder_L=_j(0, 0))  # no R
    assert compute_rig_scale(pose, _default_rig()) is None
    pose2 = JointSet(shoulder_R=_j(200, 0))  # no L
    assert compute_rig_scale(pose2, _default_rig()) is None


def test_rig_scale_returns_none_for_invalid_default_width():
    pose = JointSet(shoulder_L=_j(0, 0), shoulder_R=_j(100, 0))
    rig = RigSpec(
        identity="X",
        default_height_units=600,
        default_shoulder_width_units=0,  # invalid
        head_pivot_offset=(0, 0),
    )
    assert compute_rig_scale(pose, rig) is None


# ─── bone_angles_to_strip_frames ─────────────────────────────────


def test_bone_angles_to_strip_frames_basic():
    rig = _default_rig()
    angles = {
        "bone_arm_L_upper": 0.0,
        "bone_arm_R_upper": 90.0,
        "bone_arm_L_lower": 180.0,
        "bone_leg_L_upper": None,  # missing pose data
    }
    frames = bone_angles_to_strip_frames(angles, rig)
    assert frames["bone_arm_L_upper"] == 0
    assert frames["bone_arm_R_upper"] == 2
    assert frames["bone_arm_L_lower"] == 4
    assert frames["bone_leg_L_upper"] is None


# ─── rig_spec_from_metadata ──────────────────────────────────────


def test_rig_spec_from_metadata_full():
    meta = {
        "rig_spec_version": 1,
        "identity": "JETHALAL",
        "default_height_units": 600,
        "default_shoulder_width_units": 250,
        "head_pivot_offset": [0, -540],
        "feet_pivot_offset": [0, 0],
        "rotation_strip_angle_step": 45,
        "rotation_strip_frame_count": 8,
        "extra_field_we_dont_care_about": "yo",
    }
    rs = rig_spec_from_metadata(meta)
    assert rs.identity == "JETHALAL"
    assert rs.default_shoulder_width_units == 250.0
    assert rs.head_pivot_offset == (0.0, -540.0)
    assert rs.rotation_strip_frame_count == 8


def test_rig_spec_from_metadata_handles_defaults():
    """A minimal metadata dict uses sane defaults."""
    rs = rig_spec_from_metadata({"identity": "X"})
    assert rs.identity == "X"
    assert rs.default_height_units == 600.0
    assert rs.default_shoulder_width_units == 250.0
    assert rs.rotation_strip_angle_step == 45
    assert rs.rotation_strip_frame_count == 8


def test_rig_spec_from_metadata_handles_malformed_offsets():
    """If head/feet offsets aren't 2-tuples, fall back to (0, 0)."""
    rs = rig_spec_from_metadata({
        "identity": "X",
        "head_pivot_offset": "not a tuple",
        "feet_pivot_offset": [42],  # too short
    })
    assert rs.head_pivot_offset == (0.0, 0.0)
    assert rs.feet_pivot_offset == (0.0, 0.0)
