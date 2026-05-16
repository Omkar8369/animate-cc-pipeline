"""Unit tests for rig_validator.py.

Pure-Python tests — no Animate, no JSFL. The validator takes a
structure dict (which would normally come from
dump_rig_structure.jsfl) and runs rules against RIG_SPEC_v1.

Run via:
    <python> -m pytest animate_cc_pipeline/tests/test_rig_validator.py -v
"""

from __future__ import annotations

import json

import pytest

from animate_cc_pipeline.rig_contracts import rig_validator as rv


# ─── Helpers ────────────────────────────────────────────────────────


def _make_good_rig_structure(identity: str = "JETHALAL") -> dict:
    """Synthesize a structure dict that should pass all rules."""
    root_name = f"{identity.upper()}_RIG"
    # Build the root MovieClip's layers including switch states as
    # "children" (the validator's mental model).
    root = {
        "name": root_name,
        "kind": "movie clip",
        "frame_count": 1,
        "layers": [
            # Top-level required layers
            *[
                {"name": ln, "kind": "normal", "text_content": ""}
                for ln in rv.REQUIRED_TOP_LEVEL_LAYERS
            ],
            # Switch layers — the validator looks for children inside
            # them. Here we represent them as a single layer entry with
            # a `children` array of nested layer-like dicts.
            {
                "name": "mouth", "kind": "normal", "text_content": "",
                "children": [{"name": s} for s in rv.REQUIRED_MOUTH_STATES],
            },
            {
                "name": "eyes", "kind": "normal", "text_content": "",
                "children": [{"name": s} for s in rv.REQUIRED_EYES_STATES],
            },
            {
                "name": "eyebrows", "kind": "normal", "text_content": "",
                "children": [{"name": s} for s in rv.REQUIRED_EYEBROW_STATES],
            },
            {
                "name": "face", "kind": "normal", "text_content": "",
                "children": [{"name": s} for s in rv.REQUIRED_FACE_STATES],
            },
            # _metadata layer with valid JSON
            {
                "name": "_metadata", "kind": "normal",
                "text_content": json.dumps({
                    "rig_spec_version": 1,
                    "identity": identity,
                    "default_height_units": 600,
                    "default_shoulder_width_units": 250,
                    "head_pivot_offset": [0, -540],
                    "feet_pivot_offset": [0, 0],
                    "rotation_strip_angle_step": 45,
                    "rotation_strip_frame_count": 8,
                    "mouth_switch_path": "head/mouth",
                    "expression_switch_path": "head/face",
                    "eyes_switch_path": "head/eyes",
                    "eyebrows_switch_path": "head/eyebrows",
                    "required_bones": ["bone_torso", "bone_head"],
                }),
            },
        ],
    }
    # Each arm rotation strip is its own library item (Graphic Symbol).
    rotation_strips = [
        {"name": f"{arm}_rotation_strip", "kind": "graphic", "frame_count": 8, "layers": []}
        for arm in rv.ARM_ROTATION_STRIP_LAYERS
    ]
    return {"library_items": [root, *rotation_strips]}


# ─── Top-level smoke ────────────────────────────────────────────────


def test_good_rig_passes_all_checks():
    structure = _make_good_rig_structure("JETHALAL")
    report = rv.validate_rig_structure(structure, "rig.fla", "JETHALAL")
    assert report.passed, (
        f"good rig should pass; failures: "
        f"{[(c.rule, c.message) for c in report.failures]}"
    )
    assert len(report.checks) == len(rv.ALL_RULES)


def test_empty_structure_fails_all():
    structure = {"library_items": []}
    report = rv.validate_rig_structure(structure, "empty.fla", "JETHALAL")
    assert not report.passed
    assert len(report.failures) > 0


# ─── Per-rule tests ─────────────────────────────────────────────────


def test_missing_root_movie_clip():
    structure = {"library_items": []}
    result = rv.validate_root_movie_clip(structure, "JETHALAL")
    assert not result.passed
    assert "JETHALAL_RIG" in result.message


def test_root_movie_clip_present():
    structure = {"library_items": [{"name": "JETHALAL_RIG", "kind": "movie clip", "layers": []}]}
    result = rv.validate_root_movie_clip(structure, "JETHALAL")
    assert result.passed


def test_root_must_be_movie_clip_not_graphic():
    structure = {"library_items": [{"name": "JETHALAL_RIG", "kind": "graphic", "layers": []}]}
    result = rv.validate_root_movie_clip(structure, "JETHALAL")
    assert not result.passed


def test_top_level_layers_missing_one():
    structure = _make_good_rig_structure("JETHALAL")
    # Remove the "head" layer
    structure["library_items"][0]["layers"] = [
        l for l in structure["library_items"][0]["layers"] if l.get("name") != "head"
    ]
    result = rv.validate_top_level_layers(structure, "JETHALAL")
    assert not result.passed
    assert "head" in result.message


def test_mouth_states_missing_some():
    structure = _make_good_rig_structure("JETHALAL")
    # Remove mouth_O from the mouth switch layer's children
    for l in structure["library_items"][0]["layers"]:
        if l.get("name") == "mouth":
            l["children"] = [c for c in l["children"] if c["name"] != "mouth_O"]
    result = rv.validate_mouth_states(structure, "JETHALAL")
    assert not result.passed
    assert "mouth_O" in result.message


def test_eye_states_missing_some():
    structure = _make_good_rig_structure("JETHALAL")
    for l in structure["library_items"][0]["layers"]:
        if l.get("name") == "eyes":
            l["children"] = [c for c in l["children"] if c["name"] != "eyes_wide"]
    result = rv.validate_eye_states(structure, "JETHALAL")
    assert not result.passed
    assert "eyes_wide" in result.message


def test_eyebrow_states_missing():
    structure = _make_good_rig_structure("JETHALAL")
    for l in structure["library_items"][0]["layers"]:
        if l.get("name") == "eyebrows":
            l["children"] = []
    result = rv.validate_eyebrow_states(structure, "JETHALAL")
    assert not result.passed


def test_face_states_missing():
    structure = _make_good_rig_structure("JETHALAL")
    for l in structure["library_items"][0]["layers"]:
        if l.get("name") == "face":
            l["children"] = [{"name": "expression_neutral"}]  # missing the rest
    result = rv.validate_face_states(structure, "JETHALAL")
    assert not result.passed


def test_rotation_strips_all_present():
    structure = _make_good_rig_structure("JETHALAL")
    result = rv.validate_rotation_strips(structure, "JETHALAL")
    assert result.passed


def test_rotation_strips_missing_one():
    structure = _make_good_rig_structure("JETHALAL")
    # Remove arm_R_lower_rotation_strip
    structure["library_items"] = [
        it for it in structure["library_items"]
        if it.get("name") != "arm_R_lower_rotation_strip"
    ]
    result = rv.validate_rotation_strips(structure, "JETHALAL")
    assert not result.passed
    assert "arm_R_lower" in result.message


def test_rotation_strip_too_few_frames():
    structure = _make_good_rig_structure("JETHALAL")
    # Reduce frame count on arm_L_upper_rotation_strip
    for it in structure["library_items"]:
        if it.get("name") == "arm_L_upper_rotation_strip":
            it["frame_count"] = 3
    result = rv.validate_rotation_strips(structure, "JETHALAL")
    assert not result.passed
    assert "arm_L_upper" in result.message


def test_metadata_layer_missing():
    structure = _make_good_rig_structure("JETHALAL")
    structure["library_items"][0]["layers"] = [
        l for l in structure["library_items"][0]["layers"] if l.get("name") != "_metadata"
    ]
    result = rv.validate_metadata_layer(structure, "JETHALAL")
    assert not result.passed
    assert "_metadata" in result.message


def test_metadata_layer_invalid_json():
    structure = _make_good_rig_structure("JETHALAL")
    for l in structure["library_items"][0]["layers"]:
        if l.get("name") == "_metadata":
            l["text_content"] = "not json at all"
    result = rv.validate_metadata_layer(structure, "JETHALAL")
    assert not result.passed
    assert "JSON" in result.message


def test_metadata_layer_missing_keys():
    structure = _make_good_rig_structure("JETHALAL")
    for l in structure["library_items"][0]["layers"]:
        if l.get("name") == "_metadata":
            l["text_content"] = json.dumps({"identity": "JETHALAL"})
    result = rv.validate_metadata_layer(structure, "JETHALAL")
    assert not result.passed
    assert "missing keys" in result.message


def test_metadata_identity_mismatch():
    structure = _make_good_rig_structure("JETHALAL")
    for l in structure["library_items"][0]["layers"]:
        if l.get("name") == "_metadata":
            meta = json.loads(l["text_content"])
            meta["identity"] = "TAPPU"  # mismatch
            l["text_content"] = json.dumps(meta)
    result = rv.validate_metadata_layer(structure, "JETHALAL")
    assert not result.passed
    assert "does not match" in result.message


# ─── Report object ──────────────────────────────────────────────────


def test_validation_report_to_dict_shape():
    structure = _make_good_rig_structure("JETHALAL")
    report = rv.validate_rig_structure(structure, "rig.fla", "JETHALAL")
    d = report.to_dict()
    assert d["passed"] is True
    assert d["fla_path"] == "rig.fla"
    assert d["identity"] == "JETHALAL"
    assert d["check_count"] == len(rv.ALL_RULES)
    assert d["failure_count"] == 0
    assert isinstance(d["checks"], list)
    for c in d["checks"]:
        assert "rule" in c and "passed" in c and "message" in c


def test_validation_report_counts_failures():
    structure = {"library_items": []}
    report = rv.validate_rig_structure(structure, "empty.fla", "JETHALAL")
    d = report.to_dict()
    assert d["passed"] is False
    assert d["failure_count"] > 0
    assert d["failure_count"] == d["check_count"]  # everything fails for empty structure


def test_identity_case_insensitive_in_metadata():
    """metadata.identity comparison should be case-insensitive."""
    structure = _make_good_rig_structure("JETHALAL")
    for l in structure["library_items"][0]["layers"]:
        if l.get("name") == "_metadata":
            meta = json.loads(l["text_content"])
            meta["identity"] = "jethalal"  # lowercase in metadata
            l["text_content"] = json.dumps(meta)
    result = rv.validate_metadata_layer(structure, "JETHALAL")
    assert result.passed
