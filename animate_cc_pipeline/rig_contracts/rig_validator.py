"""Rig contract validator — validates a `.fla` against RIG_SPEC_v1.

This module is the Python side of the validator. The JSFL helper
`mcp_server/jsfl_templates/dump_rig_structure.jsfl` extracts the
rig's structure from a `.fla` as JSON; this module reads that JSON
and runs a series of validation rules.

Why split JSFL + Python? Pure-Python validation is easy to unit-test
on synthetic JSON inputs (no Animate launch needed for the rule
logic). The JSFL extraction is what actually opens the `.fla`.

What's checked (per RIG_SPEC_v1):
  - Top-level `<IDENTITY>_RIG` MovieClip exists in library
  - Required top-level layers under that MovieClip
  - Switch states (mouth phonemes, eye states, eyebrows, expressions)
  - Rotation strips for arm parts (Graphic Symbols with ≥ 8 frames)
  - `_metadata` layer with valid JSON blob

What's NOT checked (yet):
  - Armature bones / IK structure (deferred per Phase 3f scope —
    will land alongside the real rigger commission in Phase 3o /
    Phase 3f-fixup)
  - Pivot conventions (hard to verify automatically)

Returns a structured `ValidationReport` dataclass with per-rule
pass/fail flags + error messages.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ─── Required structure per RIG_SPEC_v1 ────────────────────────────


REQUIRED_TOP_LEVEL_LAYERS = [
    "head",
    "neck",
    "torso",
    "arm_L_upper",
    "arm_L_lower",
    "arm_R_upper",
    "arm_R_lower",
    "leg_L_upper",
    "leg_L_lower",
    "leg_R_upper",
    "leg_R_lower",
    "hips",
    "shoulders",
]

REQUIRED_MOUTH_STATES = [
    "mouth_neutral", "mouth_A", "mouth_E", "mouth_I",
    "mouth_O", "mouth_U", "mouth_M", "mouth_F", "mouth_L",
]

REQUIRED_EYES_STATES = ["eyes_open", "eyes_closed", "eyes_wide", "eyes_squint"]

REQUIRED_EYEBROW_STATES = [
    "eyebrows_neutral", "eyebrows_raised",
    "eyebrows_furrowed", "eyebrows_quizzical",
]

REQUIRED_FACE_STATES = [
    "expression_neutral", "expression_happy", "expression_angry",
    "expression_shocked", "expression_sad", "expression_squint",
]

ARM_ROTATION_STRIP_LAYERS = [
    "arm_L_upper", "arm_L_lower", "arm_R_upper", "arm_R_lower",
]

MIN_ROTATION_STRIP_FRAMES = 8

REQUIRED_METADATA_KEYS = [
    "rig_spec_version", "identity",
    "default_height_units", "default_shoulder_width_units",
    "head_pivot_offset", "feet_pivot_offset",
    "rotation_strip_angle_step", "rotation_strip_frame_count",
    "mouth_switch_path", "expression_switch_path",
    "eyes_switch_path", "eyebrows_switch_path",
    "required_bones",
]


# ─── Result types ──────────────────────────────────────────────────


@dataclass
class CheckResult:
    rule: str
    passed: bool
    message: str = ""


@dataclass
class ValidationReport:
    fla_path: str
    identity: str
    rig_spec_version: int = 1
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict:
        return {
            "fla_path": self.fla_path,
            "identity": self.identity,
            "rig_spec_version": self.rig_spec_version,
            "passed": self.passed,
            "check_count": len(self.checks),
            "failure_count": len(self.failures),
            "checks": [
                {"rule": c.rule, "passed": c.passed, "message": c.message}
                for c in self.checks
            ],
        }


# ─── Validation rules ──────────────────────────────────────────────


def _expected_root_symbol_name(identity: str) -> str:
    return f"{identity.upper()}_RIG"


def validate_root_movie_clip(structure: dict, identity: str) -> CheckResult:
    """The library must contain a MovieClip named <IDENTITY>_RIG."""
    expected = _expected_root_symbol_name(identity)
    library_items = structure.get("library_items", [])
    for item in library_items:
        if item.get("name") == expected and item.get("kind") == "movie clip":
            return CheckResult("root_movie_clip", True, f"found '{expected}'")
    return CheckResult(
        "root_movie_clip", False,
        f"library is missing MovieClip '{expected}' "
        f"(library has {len(library_items)} item(s))",
    )


def validate_top_level_layers(structure: dict, identity: str) -> CheckResult:
    """The root rig MovieClip must contain the required top-level layers."""
    expected = _expected_root_symbol_name(identity)
    library_items = structure.get("library_items", [])
    root = next(
        (it for it in library_items if it.get("name") == expected and it.get("kind") == "movie clip"),
        None,
    )
    if root is None:
        return CheckResult(
            "top_level_layers", False,
            f"cannot check — root MovieClip '{expected}' missing",
        )
    layer_names = {l.get("name") for l in root.get("layers", [])}
    missing = [name for name in REQUIRED_TOP_LEVEL_LAYERS if name not in layer_names]
    if missing:
        return CheckResult(
            "top_level_layers", False,
            f"missing layers: {', '.join(missing)}",
        )
    return CheckResult(
        "top_level_layers", True,
        f"all {len(REQUIRED_TOP_LEVEL_LAYERS)} required layers present",
    )


def _find_switch_states(structure: dict, identity: str, switch_layer_name: str) -> list[str]:
    """Return the list of child-layer names inside a named switch layer."""
    expected = _expected_root_symbol_name(identity)
    library_items = structure.get("library_items", [])
    root = next(
        (it for it in library_items if it.get("name") == expected and it.get("kind") == "movie clip"),
        None,
    )
    if root is None:
        return []
    for layer in root.get("layers", []):
        if layer.get("name") == switch_layer_name:
            return [child.get("name") for child in layer.get("children", [])]
    return []


def _validate_switch(
    structure: dict, identity: str, switch_layer_name: str,
    required_states: list[str], rule_name: str,
) -> CheckResult:
    states = _find_switch_states(structure, identity, switch_layer_name)
    if not states:
        return CheckResult(
            rule_name, False,
            f"switch layer '{switch_layer_name}' not found or empty",
        )
    missing = [s for s in required_states if s not in states]
    if missing:
        return CheckResult(
            rule_name, False,
            f"missing states in '{switch_layer_name}': {', '.join(missing)}",
        )
    return CheckResult(
        rule_name, True,
        f"all {len(required_states)} states present in '{switch_layer_name}'",
    )


def validate_mouth_states(structure: dict, identity: str) -> CheckResult:
    return _validate_switch(
        structure, identity, "mouth", REQUIRED_MOUTH_STATES, "mouth_states",
    )


def validate_eye_states(structure: dict, identity: str) -> CheckResult:
    return _validate_switch(
        structure, identity, "eyes", REQUIRED_EYES_STATES, "eye_states",
    )


def validate_eyebrow_states(structure: dict, identity: str) -> CheckResult:
    return _validate_switch(
        structure, identity, "eyebrows", REQUIRED_EYEBROW_STATES, "eyebrow_states",
    )


def validate_face_states(structure: dict, identity: str) -> CheckResult:
    return _validate_switch(
        structure, identity, "face", REQUIRED_FACE_STATES, "face_states",
    )


def validate_rotation_strips(structure: dict, identity: str) -> CheckResult:
    """Each arm part must contain a Graphic Symbol with >= 8 frames."""
    expected = _expected_root_symbol_name(identity)
    library_items = structure.get("library_items", [])
    root = next(
        (it for it in library_items if it.get("name") == expected and it.get("kind") == "movie clip"),
        None,
    )
    if root is None:
        return CheckResult(
            "rotation_strips", False,
            f"cannot check — root MovieClip '{expected}' missing",
        )
    # Build name -> graphic-frame-count map for library items
    graphic_frames: dict[str, int] = {}
    for item in library_items:
        if item.get("kind") == "graphic":
            graphic_frames[item.get("name", "")] = item.get("frame_count", 0)

    issues = []
    for arm_layer_name in ARM_ROTATION_STRIP_LAYERS:
        # Find the layer
        layer = next(
            (l for l in root.get("layers", []) if l.get("name") == arm_layer_name),
            None,
        )
        if layer is None:
            issues.append(f"{arm_layer_name}: layer missing")
            continue
        # Layer should contain an instance whose library item is a Graphic
        # Symbol with >= MIN_ROTATION_STRIP_FRAMES frames.
        strip_name = f"{arm_layer_name}_rotation_strip"
        if strip_name not in graphic_frames:
            issues.append(f"{arm_layer_name}: no library Graphic Symbol named '{strip_name}'")
            continue
        if graphic_frames[strip_name] < MIN_ROTATION_STRIP_FRAMES:
            issues.append(
                f"{arm_layer_name}: '{strip_name}' has only "
                f"{graphic_frames[strip_name]} frames "
                f"(need ≥ {MIN_ROTATION_STRIP_FRAMES})"
            )

    if issues:
        return CheckResult("rotation_strips", False, "; ".join(issues))
    return CheckResult(
        "rotation_strips", True,
        f"all {len(ARM_ROTATION_STRIP_LAYERS)} arm rotation strips valid",
    )


def validate_metadata_layer(structure: dict, identity: str) -> CheckResult:
    """A `_metadata` layer must contain a JSON blob with required keys."""
    expected = _expected_root_symbol_name(identity)
    library_items = structure.get("library_items", [])
    root = next(
        (it for it in library_items if it.get("name") == expected and it.get("kind") == "movie clip"),
        None,
    )
    if root is None:
        return CheckResult(
            "metadata_layer", False,
            f"cannot check — root MovieClip '{expected}' missing",
        )
    metadata_layer = next(
        (l for l in root.get("layers", []) if l.get("name") == "_metadata"),
        None,
    )
    if metadata_layer is None:
        return CheckResult("metadata_layer", False, "_metadata layer not found")
    raw_text = metadata_layer.get("text_content", "").strip()
    if not raw_text:
        return CheckResult(
            "metadata_layer", False,
            "_metadata layer found but text_content is empty",
        )
    try:
        meta = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return CheckResult(
            "metadata_layer", False,
            f"_metadata text is not valid JSON: {exc}",
        )
    if not isinstance(meta, dict):
        return CheckResult(
            "metadata_layer", False,
            f"_metadata JSON must be an object; got {type(meta).__name__}",
        )
    missing_keys = [k for k in REQUIRED_METADATA_KEYS if k not in meta]
    if missing_keys:
        return CheckResult(
            "metadata_layer", False,
            f"_metadata JSON missing keys: {', '.join(missing_keys)}",
        )
    declared_identity = meta.get("identity", "")
    if declared_identity.upper() != identity.upper():
        return CheckResult(
            "metadata_layer", False,
            f"_metadata.identity ({declared_identity!r}) does not match "
            f"validate_rig() identity arg ({identity!r})",
        )
    return CheckResult(
        "metadata_layer", True,
        f"_metadata JSON valid; identity={declared_identity}",
    )


# ─── Top-level entry point ─────────────────────────────────────────


ALL_RULES = [
    validate_root_movie_clip,
    validate_top_level_layers,
    validate_mouth_states,
    validate_eye_states,
    validate_eyebrow_states,
    validate_face_states,
    validate_rotation_strips,
    validate_metadata_layer,
]


def validate_rig_structure(structure: dict, fla_path: str, identity: str) -> ValidationReport:
    """Run all rules against the parsed structure JSON. Pure function;
    no filesystem or Animate access.
    """
    report = ValidationReport(fla_path=fla_path, identity=identity)
    for rule_fn in ALL_RULES:
        try:
            result = rule_fn(structure, identity)
        except Exception as exc:  # pragma: no cover
            result = CheckResult(
                rule_fn.__name__,
                False,
                f"rule raised: {type(exc).__name__}: {exc}",
            )
        report.checks.append(result)
    return report


def validate_rig_from_json_file(json_path: Path | str, fla_path: str, identity: str) -> ValidationReport:
    """Read the JSFL-produced structure JSON, then validate."""
    json_path = Path(json_path)
    structure = json.loads(json_path.read_text(encoding="utf-8"))
    return validate_rig_structure(structure, fla_path, identity)
