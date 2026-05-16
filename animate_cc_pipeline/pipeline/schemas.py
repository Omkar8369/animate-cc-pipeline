"""Schemas (pydantic v2) for Node 6 pose estimation outputs.

Two files written per pipeline run:

  pose_map.json (one per shot)
    → per-frame per-character joint coordinates

  node6_result.json (one aggregate)
    → summary across all shots; pointers to per-shot pose_map.json
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict


# ─── Joint identifiers ─────────────────────────────────────────────


JOINT_NAMES = [
    "nose",
    "neck",
    "shoulder_L",
    "shoulder_R",
    "elbow_L",
    "elbow_R",
    "wrist_L",
    "wrist_R",
    "hip_L",
    "hip_R",
    "knee_L",
    "knee_R",
    "ankle_L",
    "ankle_R",
]


# ─── Building blocks ───────────────────────────────────────────────


class Joint(BaseModel):
    """A single joint location in image-frame coords (pixels)."""
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    confidence: float = Field(ge=0.0, le=1.0)


class JointSet(BaseModel):
    """A character's joints for one frame.

    Each joint may be `None` if the pose estimator's confidence was
    below threshold or the joint was occluded. Consumers should
    handle nulls — the orchestrator falls back to interpolating from
    the previous reliable frame.
    """
    model_config = ConfigDict(extra="forbid")

    nose: Joint | None = None
    neck: Joint | None = None
    shoulder_L: Joint | None = None
    shoulder_R: Joint | None = None
    elbow_L: Joint | None = None
    elbow_R: Joint | None = None
    wrist_L: Joint | None = None
    wrist_R: Joint | None = None
    hip_L: Joint | None = None
    hip_R: Joint | None = None
    knee_L: Joint | None = None
    knee_R: Joint | None = None
    ankle_L: Joint | None = None
    ankle_R: Joint | None = None


class Bbox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int
    w: int
    h: int


class CharacterPose(BaseModel):
    """One character's pose data on one frame."""
    model_config = ConfigDict(extra="forbid")

    identity: str
    bbox: Bbox
    joints: JointSet


class FramePoseSet(BaseModel):
    """All characters' poses on one frame."""
    model_config = ConfigDict(extra="forbid")

    frameIndex: int = Field(ge=1)
    characters: list[CharacterPose] = Field(default_factory=list)


class PoseMap(BaseModel):
    """Top-level pose_map.json shape (one per shot)."""
    model_config = ConfigDict(extra="forbid")

    schemaVersion: int = Field(default=1, ge=1)
    shotId: str
    frames: dict[str, FramePoseSet] = Field(default_factory=dict)
    """Keyed by 1-indexed frame number as a string (JSON keys must
    be strings, and the orchestrator does the int→str conversion)."""


# ─── Aggregate ─────────────────────────────────────────────────────


class ShotPoseSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shotId: str
    framesProcessed: int = Field(ge=0)
    charactersFound: int = Field(ge=0)
    poseMapPath: str


class Node6Result(BaseModel):
    """Top-level node6_result.json shape (aggregate over all shots)."""
    model_config = ConfigDict(extra="forbid")

    schemaVersion: int = Field(default=1, ge=1)
    backend: str
    """Which pose backend was used (e.g. 'mock', 'http', 'dwpose_local')."""
    shots: list[ShotPoseSummary] = Field(default_factory=list)
