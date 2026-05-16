"""Typed error hierarchy for pipeline Nodes.

Follows the prior `animatic-refinement` project's convention: each
Node has its own subclass of `PipelineError`. CLI dispatch uses
the type for exit-code categorization.
"""

from __future__ import annotations


class PipelineError(Exception):
    """Base class for all pipeline-Node errors."""


# ─── Node 6 (per-frame pose estimation) ────────────────────────────


class Node6Error(PipelineError):
    """Base class for Node 6 errors."""


class Node5ResultInputError(Node6Error):
    """The supplied node5_result.json is missing, malformed, or has
    the wrong schemaVersion."""


class FramesDirInputError(Node6Error):
    """A shot's frames directory is missing or empty."""


class PoseBackendError(Node6Error):
    """Underlying pose estimator failed (e.g. HTTP error, model load
    failure). For per-character soft-failures the CLI logs and
    continues; this is for show-stoppers."""


class PoseMapOutputError(Node6Error):
    """Could not write pose_map.json / node6_result.json to disk."""
