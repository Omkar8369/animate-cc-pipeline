"""Schemas (pydantic v2) for orchestrator inputs + outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─── Inputs ───────────────────────────────────────────────────────


class CharacterConfig(BaseModel):
    """Per-character input to the shot processor.

    Exactly one of `rig_fla_path` (production) or
    `placeholder_image_path` (smoke / testing) must be set. The
    processor adapts which MCP tools it calls based on which is set.
    """
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    identity: str
    rig_fla_path: Optional[Path] = None
    placeholder_image_path: Optional[Path] = None
    pose_map_path: Optional[Path] = None
    """Path to this character's pose_map.json (from Node 6 /
    Phase 3j). If None, the character will be placed at frame 1
    only without any per-frame animation."""

    def has_rig(self) -> bool:
        return self.rig_fla_path is not None

    def has_placeholder(self) -> bool:
        return self.placeholder_image_path is not None


class ShotConfig(BaseModel):
    """All inputs for processing one shot."""
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    shot_id: str
    fla_out_path: Path
    """Where the orchestrator writes the assembled .fla."""
    mp4_out_path: Optional[Path] = None
    """If set, the orchestrator renders to MP4 after .fla save."""

    animatic_mp4_path: Optional[Path] = None
    """Rough animatic MP4 (used as low-opacity reference layer in the
    composition). Optional — operator may skip if not desired."""

    background_image_path: Optional[Path] = None
    """Background plate for the scene (location). Optional."""

    audio_wav_path: Optional[Path] = None
    """Hindi voice / dialogue audio. Optional."""

    camera_moves_path: Optional[Path] = None
    """Path to camera_moves.json produced by Phase 3m's camera_detector
    CLI (or any consumer that emits the `CameraMovesMap` schema). If
    set, the orchestrator calls set_camera_position per CameraState
    entry so the rendered MP4 mirrors the rough animatic's camera work.
    Optional — operator may skip if the shot has a static camera."""

    characters: list[CharacterConfig] = Field(default_factory=list)

    width: int = 1920
    height: int = 1080
    fps: int = 25


# ─── Outputs ──────────────────────────────────────────────────────


class StepResult(BaseModel):
    """One step's outcome inside shot processing."""
    model_config = ConfigDict(extra="forbid")

    step: str
    ok: bool
    elapsed_seconds: float = 0.0
    note: str = ""


class ShotAssembly(BaseModel):
    """Per-shot output of the orchestrator."""
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    shot_id: str
    success: bool
    fla_out_path: Optional[Path] = None
    mp4_out_path: Optional[Path] = None
    total_elapsed_seconds: float = 0.0
    keyposes_processed: int = 0
    characters_assembled: int = 0
    warnings: list[str] = Field(default_factory=list)
    steps: list[StepResult] = Field(default_factory=list)


class AssemblyReport(BaseModel):
    """Aggregate report across all shots in a batch run."""
    model_config = ConfigDict(extra="forbid")

    schemaVersion: int = 1
    shots: list[ShotAssembly] = Field(default_factory=list)

    @property
    def num_succeeded(self) -> int:
        return sum(1 for s in self.shots if s.success)

    @property
    def num_failed(self) -> int:
        return sum(1 for s in self.shots if not s.success)
