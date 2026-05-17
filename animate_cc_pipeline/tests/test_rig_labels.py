"""Unit tests for rig_labels (Phase 3o-adapter).

Most checks use synthetic XML / sidecar JSON. The one integration
test against a real .fla is gated on file presence — skipped on
machines without the operator's character pack.

Run via:
    <python> -m pytest animate_cc_pipeline/tests/test_rig_labels.py -v
"""

from __future__ import annotations

import io
import json
import struct
import zipfile
from pathlib import Path

import pytest

from animate_cc_pipeline.pipeline.rig_labels import (
    PLACEHOLDER,
    STANDARD_ANGLE_LABELS,
    RigLabels,
    RigPlacement,
    _parse_dom_xml,
    _read_fla_zip_lenient,
    extract_placements_from_fla,
    initialize_labels_for_rig,
    load_labels,
    resolve_identity_via_sidecar,
    save_labels,
    sidecar_path_for,
)


# ─── Schemas ──────────────────────────────────────────────────────


def test_rig_placement_defaults_to_placeholder_label():
    p = RigPlacement(index=1, x_pos=100.0, y_pos=200.0, library_name="foo")
    assert p.label == PLACEHOLDER


def test_rig_placement_extra_field_forbidden():
    with pytest.raises(Exception):
        RigPlacement.model_validate({
            "index": 1, "x_pos": 0, "y_pos": 0,
            "library_name": "foo", "garbage": True,
        })


def test_rig_placement_index_must_be_positive():
    with pytest.raises(Exception):
        RigPlacement(index=0, x_pos=0, y_pos=0, library_name="foo")


def test_rig_labels_round_trip():
    labels = RigLabels(
        character="JETHALAL",
        rig_fla_filename="JETHALAL.fla",
        labels={"front": "fgbfgfgn"},
        by_position=[
            RigPlacement(index=1, x_pos=100, y_pos=200,
                         library_name="fgbfgfgn", label="front"),
        ],
    )
    serialized = labels.model_dump_json()
    reloaded = RigLabels.model_validate_json(serialized)
    assert reloaded.character == "JETHALAL"
    assert reloaded.labels["front"] == "fgbfgfgn"
    assert len(reloaded.by_position) == 1


def test_rig_labels_resolve_via_label():
    labels = RigLabels(
        character="X",
        rig_fla_filename="x.fla",
        labels={"front": "real_name"},
        by_position=[
            RigPlacement(index=1, x_pos=0, y_pos=0,
                         library_name="real_name", label="front"),
        ],
    )
    assert labels.resolve("front") == "real_name"


def test_rig_labels_resolve_passthrough_for_direct_name():
    """If the caller passes a direct library name that appears in
    by_position, resolve passes it through unchanged."""
    labels = RigLabels(
        character="X",
        rig_fla_filename="x.fla",
        labels={"front": "real_name"},
        by_position=[
            RigPlacement(index=1, x_pos=0, y_pos=0,
                         library_name="real_name", label="front"),
            RigPlacement(index=2, x_pos=100, y_pos=0,
                         library_name="other_name"),
        ],
    )
    # "real_name" is both a label target AND a library name; via
    # labels: "front" → "real_name" (already tested).
    # via direct library name: "other_name" → "other_name"
    assert labels.resolve("other_name") == "other_name"


def test_rig_labels_resolve_returns_none_for_unknown():
    labels = RigLabels(
        character="X",
        rig_fla_filename="x.fla",
        labels={"front": "a"},
        by_position=[
            RigPlacement(index=1, x_pos=0, y_pos=0, library_name="a", label="front"),
        ],
    )
    assert labels.resolve("nonexistent_label") is None


def test_rig_labels_filled_count():
    labels = RigLabels(
        character="X",
        rig_fla_filename="x.fla",
        by_position=[
            RigPlacement(index=1, x_pos=0, y_pos=0, library_name="a", label="front"),
            RigPlacement(index=2, x_pos=100, y_pos=0, library_name="b"),  # PLACEHOLDER
            RigPlacement(index=3, x_pos=200, y_pos=0, library_name="c", label="back"),
        ],
    )
    assert labels.filled_count() == 2


def test_standard_angle_labels_have_expected_entries():
    """Sanity: STANDARD_ANGLE_LABELS contains the basic turnaround
    angles we expect operators to use."""
    assert "front" in STANDARD_ANGLE_LABELS
    assert "back" in STANDARD_ANGLE_LABELS
    assert any("side" in s for s in STANDARD_ANGLE_LABELS)


# ─── DOMDocument.xml parser ──────────────────────────────────────


def _build_dom_xml(placements: list[tuple[str, float, float]]) -> bytes:
    """Build a minimal DOMDocument.xml that matches the structure
    `_parse_dom_xml` walks."""
    ns = "http://ns.adobe.com/xfl/2008/"
    parts = [
        f'<DOMDocument xmlns="{ns}">',
        '<timelines><DOMTimeline name="Scene 1"><layers><DOMLayer name="L"><frames><DOMFrame index="0">',
        '<elements>',
    ]
    for name, tx, ty in placements:
        parts.append(
            f'<DOMSymbolInstance libraryItemName="{name}" symbolType="graphic" loop="loop">'
            f'<matrix><Matrix tx="{tx}" ty="{ty}"/></matrix>'
            '</DOMSymbolInstance>'
        )
    parts.append('</elements></DOMFrame></frames></DOMLayer></layers></DOMTimeline></timelines></DOMDocument>')
    return "".join(parts).encode("utf-8")


def test_parse_dom_xml_extracts_graphic_symbols():
    xml = _build_dom_xml([
        ("back_pose", 2000, 100),
        ("front_pose", 500, 100),
        ("side_pose", 1000, 100),
    ])
    placements = _parse_dom_xml(xml)
    assert len(placements) == 3
    # Sorted left-to-right by x_pos
    assert placements[0].library_name == "front_pose"
    assert placements[0].index == 1
    assert placements[1].library_name == "side_pose"
    assert placements[2].library_name == "back_pose"


def test_parse_dom_xml_ignores_non_graphic_symbols():
    """MovieClip symbols and bitmap instances should be skipped."""
    ns = "http://ns.adobe.com/xfl/2008/"
    xml = (
        f'<DOMDocument xmlns="{ns}">'
        '<elements>'
        '<DOMSymbolInstance libraryItemName="a_clip" symbolType="movieclip">'
        '<matrix><Matrix tx="0" ty="0"/></matrix></DOMSymbolInstance>'
        '<DOMSymbolInstance libraryItemName="a_graphic" symbolType="graphic">'
        '<matrix><Matrix tx="100" ty="0"/></matrix></DOMSymbolInstance>'
        '<DOMBitmapInstance libraryItemName="some_image"/>'
        '</elements></DOMDocument>'
    ).encode("utf-8")
    placements = _parse_dom_xml(xml)
    assert len(placements) == 1
    assert placements[0].library_name == "a_graphic"


def test_parse_dom_xml_handles_missing_matrix():
    """A symbol with no Matrix child should default to (0, 0)."""
    ns = "http://ns.adobe.com/xfl/2008/"
    xml = (
        f'<DOMDocument xmlns="{ns}">'
        '<DOMSymbolInstance libraryItemName="no_matrix" symbolType="graphic"/>'
        '</DOMDocument>'
    ).encode("utf-8")
    placements = _parse_dom_xml(xml)
    assert len(placements) == 1
    assert placements[0].x_pos == 0
    assert placements[0].y_pos == 0


def test_parse_dom_xml_empty_doc():
    ns = "http://ns.adobe.com/xfl/2008/"
    xml = f'<DOMDocument xmlns="{ns}"></DOMDocument>'.encode("utf-8")
    assert _parse_dom_xml(xml) == []


# ─── _read_fla_zip_lenient ────────────────────────────────────────


def _make_xfl_fla(tmp_path: Path, dom_xml: bytes, *, corrupt_cd_size_by: int = 0) -> Path:
    """Build a synthetic .fla zip. If corrupt_cd_size_by > 0,
    over-claim the central-directory size by that many bytes —
    mimics Adobe's non-standard XFL format."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("DOMDocument.xml", dom_xml)
    raw = buf.getvalue()

    if corrupt_cd_size_by > 0:
        # Patch the EOCD's cd_size field to be `corrupt_cd_size_by`
        # bytes higher than real, to simulate Adobe's misreporting.
        eocd_idx = raw.rfind(b"PK\x05\x06")
        cd_size_field_off = eocd_idx + 12
        current = struct.unpack_from("<I", raw, cd_size_field_off)[0]
        raw = bytearray(raw)
        struct.pack_into("<I", raw, cd_size_field_off, current + corrupt_cd_size_by)
        raw = bytes(raw)

    p = tmp_path / "test.fla"
    p.write_bytes(raw)
    return p


def test_read_fla_zip_lenient_normal_zip(tmp_path):
    """Plain valid zip — should work."""
    dom = b"<DOMDocument/>"
    p = _make_xfl_fla(tmp_path, dom)
    zf = _read_fla_zip_lenient(p)
    try:
        assert zf.read("DOMDocument.xml") == dom
    finally:
        zf.close()


def test_read_fla_zip_lenient_handles_oversized_cd(tmp_path):
    """The Adobe Animate misfeature: cd_size in EOCD is 54 bytes
    too large. The lenient reader patches it."""
    dom = b"<DOMDocument/>"
    p = _make_xfl_fla(tmp_path, dom, corrupt_cd_size_by=54)
    zf = _read_fla_zip_lenient(p)
    try:
        assert zf.read("DOMDocument.xml") == dom
    finally:
        zf.close()


def test_read_fla_zip_lenient_missing_eocd_raises(tmp_path):
    p = tmp_path / "not_a_zip.fla"
    p.write_bytes(b"this is not a zip file at all")
    with pytest.raises(ValueError, match="no EOCD signature"):
        _read_fla_zip_lenient(p)


# ─── extract_placements_from_fla ──────────────────────────────────


def test_extract_placements_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_placements_from_fla(tmp_path / "missing.fla")


def test_extract_placements_from_synthetic_fla(tmp_path):
    dom = _build_dom_xml([
        ("right_pose", 2000, 100),
        ("left_pose", 100, 100),
    ])
    fla = _make_xfl_fla(tmp_path, dom)
    placements = extract_placements_from_fla(fla)
    assert [p.library_name for p in placements] == ["left_pose", "right_pose"]


def test_extract_placements_missing_dom_xml(tmp_path):
    """A zip without DOMDocument.xml should raise ValueError."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("other.txt", b"hello")
    fla = tmp_path / "no_dom.fla"
    fla.write_bytes(buf.getvalue())
    with pytest.raises(ValueError, match="DOMDocument.xml"):
        extract_placements_from_fla(fla)


# ─── Sidecar I/O ──────────────────────────────────────────────────


def test_sidecar_path_for():
    p = Path("/some/where/jethalal.fla")
    assert sidecar_path_for(p) == Path("/some/where/jethalal.fla.labels.json")


def test_save_then_load_round_trip(tmp_path):
    labels = RigLabels(
        character="X",
        rig_fla_filename="x.fla",
        by_position=[
            RigPlacement(index=1, x_pos=100, y_pos=0, library_name="lib_a", label="front"),
            RigPlacement(index=2, x_pos=200, y_pos=0, library_name="lib_b"),
        ],
    )
    sidecar = tmp_path / "x.fla.labels.json"
    save_labels(sidecar, labels)
    assert sidecar.exists()

    reloaded = load_labels(sidecar)
    assert reloaded.character == "X"
    # save_labels refreshed the labels map from by_position
    assert reloaded.labels == {"front": "lib_a"}


def test_save_labels_refreshes_label_map(tmp_path):
    """save_labels rebuilds .labels from by_position so stale entries
    in .labels are dropped."""
    labels = RigLabels(
        character="X",
        rig_fla_filename="x.fla",
        labels={"stale_label": "should_be_gone"},
        by_position=[
            RigPlacement(index=1, x_pos=0, y_pos=0, library_name="a", label="front"),
        ],
    )
    sidecar = tmp_path / "x.fla.labels.json"
    save_labels(sidecar, labels)
    reloaded = load_labels(sidecar)
    assert "stale_label" not in reloaded.labels
    assert reloaded.labels == {"front": "a"}


def test_load_missing_sidecar_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_labels(tmp_path / "nope.labels.json")


def test_initialize_labels_from_synthetic_fla(tmp_path):
    dom = _build_dom_xml([("p1", 100, 0), ("p2", 200, 0)])
    fla = _make_xfl_fla(tmp_path, dom)
    labels = initialize_labels_for_rig(fla, character="TEST")
    assert labels.character == "TEST"
    assert labels.rig_fla_filename == fla.name
    assert len(labels.by_position) == 2
    # All placements start as PLACEHOLDER
    for p in labels.by_position:
        assert p.label == PLACEHOLDER


# ─── resolve_identity_via_sidecar ────────────────────────────────


def test_resolve_identity_no_sidecar_passthrough(tmp_path):
    """If no sidecar, identity passes through unchanged."""
    fla = tmp_path / "no_sidecar.fla"
    fla.write_bytes(b"")
    resolved, sidecar = resolve_identity_via_sidecar(fla, "anything")
    assert resolved == "anything"
    assert sidecar is None


def test_resolve_identity_via_sidecar_label(tmp_path):
    """With a sidecar holding `front -> real_name`, identity='front'
    resolves to 'real_name'."""
    fla = tmp_path / "x.fla"; fla.write_bytes(b"")
    labels = RigLabels(
        character="X", rig_fla_filename="x.fla",
        by_position=[
            RigPlacement(index=1, x_pos=0, y_pos=0,
                         library_name="real_name", label="front"),
        ],
    )
    save_labels(sidecar_path_for(fla), labels)

    resolved, sidecar = resolve_identity_via_sidecar(fla, "front")
    assert resolved == "real_name"
    assert sidecar == sidecar_path_for(fla)


def test_resolve_identity_via_sidecar_unknown_passthrough(tmp_path):
    """Unknown identity → return unchanged + sidecar path."""
    fla = tmp_path / "x.fla"; fla.write_bytes(b"")
    labels = RigLabels(
        character="X", rig_fla_filename="x.fla",
        by_position=[
            RigPlacement(index=1, x_pos=0, y_pos=0,
                         library_name="real_name", label="front"),
        ],
    )
    save_labels(sidecar_path_for(fla), labels)

    resolved, sidecar = resolve_identity_via_sidecar(fla, "mystery")
    assert resolved == "mystery"
    assert sidecar == sidecar_path_for(fla)


def test_resolve_identity_via_sidecar_invalid_json(tmp_path):
    """Corrupt sidecar → pass-through (graceful degradation)."""
    fla = tmp_path / "x.fla"; fla.write_bytes(b"")
    sidecar = sidecar_path_for(fla)
    sidecar.write_text("not valid json {", encoding="utf-8")
    resolved, used = resolve_identity_via_sidecar(fla, "front")
    assert resolved == "front"
    assert used is None


# ─── Real-rig integration (skipped if files absent) ──────────────


_REAL_JETHALAL = Path(
    r"C:\Users\Omkar Hajare\Downloads\CHARACTER\CHARACTER\JETHALAL_Turnaround_FINAL.fla"
)


@pytest.mark.skipif(
    not _REAL_JETHALAL.exists(),
    reason="real Jethalal rig not present on this machine",
)
def test_real_jethalal_parses_to_7_placements():
    """Sanity smoke: against the real rigger-delivered file."""
    placements = extract_placements_from_fla(_REAL_JETHALAL)
    assert len(placements) == 7
    # Leftmost should be x≈366
    assert placements[0].x_pos < 500
    # Library names should all be non-empty obfuscated strings
    for p in placements:
        assert p.library_name
        assert len(p.library_name) >= 3
