"""CLI tests for tools/phase3/rig_labeler.py.

Run via:
    <python> -m pytest animate_cc_pipeline/tests/test_rig_labeler_cli.py -v
"""

from __future__ import annotations

import io
import json
import struct
import sys
import zipfile
from pathlib import Path

import pytest

# Make tools/phase3 importable
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.phase3 import rig_labeler

from animate_cc_pipeline.pipeline.rig_labels import (
    PLACEHOLDER,
    RigLabels,
    RigPlacement,
    save_labels,
    sidecar_path_for,
)


# ─── Helpers ──────────────────────────────────────────────────────


def _build_minimal_fla(tmp_path: Path, names_and_x: list[tuple[str, float]]) -> Path:
    """Build a synthetic .fla zip with a DOMDocument.xml that declares
    the given graphic-symbol placements on the main timeline."""
    ns = "http://ns.adobe.com/xfl/2008/"
    elements = "".join(
        f'<DOMSymbolInstance libraryItemName="{name}" symbolType="graphic">'
        f'<matrix><Matrix tx="{x}" ty="0"/></matrix>'
        '</DOMSymbolInstance>'
        for name, x in names_and_x
    )
    dom = (
        f'<DOMDocument xmlns="{ns}">'
        f'<timelines><DOMTimeline><layers><DOMLayer><frames><DOMFrame>'
        f'<elements>{elements}</elements>'
        f'</DOMFrame></frames></DOMLayer></layers></DOMTimeline></timelines>'
        f'</DOMDocument>'
    ).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("DOMDocument.xml", dom)
    p = tmp_path / "test_rig.fla"
    p.write_bytes(buf.getvalue())
    return p


# ─── --init ───────────────────────────────────────────────────────


def test_init_writes_sidecar(tmp_path, capsys):
    fla = _build_minimal_fla(tmp_path, [("front_p", 100), ("back_p", 200)])
    rc = rig_labeler.main([
        "--rig", str(fla),
        "--character", "TEST_CHAR",
        "--init",
        "--log-level", "ERROR",
    ])
    assert rc == 0
    sidecar = sidecar_path_for(fla)
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["character"] == "TEST_CHAR"
    assert len(data["by_position"]) == 2
    # All placements start as PLACEHOLDER
    for p in data["by_position"]:
        assert p["label"] == PLACEHOLDER
    # Labels map is empty (no filled-in entries yet)
    assert data["labels"] == {}


def test_init_requires_character(tmp_path):
    fla = _build_minimal_fla(tmp_path, [("a", 0)])
    rc = rig_labeler.main([
        "--rig", str(fla),
        "--init",
        "--log-level", "ERROR",
    ])
    assert rc == 2


def test_init_missing_rig_returns_2(tmp_path):
    rc = rig_labeler.main([
        "--rig", str(tmp_path / "no_such.fla"),
        "--character", "X",
        "--init",
        "--log-level", "ERROR",
    ])
    assert rc == 2


def test_init_refuses_overwrite_without_force(tmp_path):
    fla = _build_minimal_fla(tmp_path, [("a", 0)])
    sidecar = sidecar_path_for(fla)
    sidecar.write_text("{}", encoding="utf-8")  # pre-existing
    rc = rig_labeler.main([
        "--rig", str(fla),
        "--character", "X",
        "--init",
        "--log-level", "ERROR",
    ])
    assert rc == 2


def test_init_force_overwrites(tmp_path):
    fla = _build_minimal_fla(tmp_path, [("a", 0)])
    sidecar = sidecar_path_for(fla)
    sidecar.write_text("old content", encoding="utf-8")
    rc = rig_labeler.main([
        "--rig", str(fla),
        "--character", "X",
        "--init",
        "--force",
        "--log-level", "ERROR",
    ])
    assert rc == 0
    # File was rewritten as valid JSON
    json.loads(sidecar.read_text(encoding="utf-8"))


def test_init_with_explicit_sidecar_path(tmp_path):
    fla = _build_minimal_fla(tmp_path, [("a", 0)])
    custom = tmp_path / "subdir" / "custom.labels.json"
    rc = rig_labeler.main([
        "--rig", str(fla),
        "--character", "X",
        "--sidecar", str(custom),
        "--init",
        "--log-level", "ERROR",
    ])
    assert rc == 0
    assert custom.exists()
    # Default sidecar was NOT written
    assert not sidecar_path_for(fla).exists()


# ─── --verify ─────────────────────────────────────────────────────


def test_verify_passes_when_some_labels_filled(tmp_path):
    fla = _build_minimal_fla(tmp_path, [("a", 0)])
    labels = RigLabels(
        character="X",
        rig_fla_filename=fla.name,
        by_position=[
            RigPlacement(index=1, x_pos=0, y_pos=0,
                         library_name="a", label="front"),
        ],
    )
    save_labels(sidecar_path_for(fla), labels)
    rc = rig_labeler.main([
        "--rig", str(fla),
        "--verify",
        "--log-level", "ERROR",
    ])
    assert rc == 0


def test_verify_fails_when_no_labels_filled(tmp_path):
    fla = _build_minimal_fla(tmp_path, [("a", 0)])
    labels = RigLabels(
        character="X",
        rig_fla_filename=fla.name,
        by_position=[
            RigPlacement(index=1, x_pos=0, y_pos=0, library_name="a"),
        ],
    )
    save_labels(sidecar_path_for(fla), labels)
    rc = rig_labeler.main([
        "--rig", str(fla),
        "--verify",
        "--log-level", "ERROR",
    ])
    assert rc == 1


def test_verify_missing_sidecar_returns_2(tmp_path):
    fla = _build_minimal_fla(tmp_path, [("a", 0)])
    rc = rig_labeler.main([
        "--rig", str(fla),
        "--verify",
        "--log-level", "ERROR",
    ])
    assert rc == 2


def test_verify_warns_on_filename_mismatch(tmp_path, capsys):
    """Sidecar's rig_fla_filename should match the rig basename."""
    fla = _build_minimal_fla(tmp_path, [("a", 0)])
    labels = RigLabels(
        character="X",
        rig_fla_filename="SOMETHING_ELSE.fla",  # mismatched
        by_position=[
            RigPlacement(index=1, x_pos=0, y_pos=0,
                         library_name="a", label="front"),
        ],
    )
    save_labels(sidecar_path_for(fla), labels)
    rc = rig_labeler.main([
        "--rig", str(fla),
        "--verify",
        "--log-level", "ERROR",
    ])
    assert rc == 0  # still OK overall — just a warning
    out = capsys.readouterr().out
    assert "WARNING" in out


# ─── --list ───────────────────────────────────────────────────────


def test_list_prints_placements(tmp_path, capsys):
    fla = _build_minimal_fla(tmp_path, [("a", 0), ("b", 100)])
    labels = RigLabels(
        character="X",
        rig_fla_filename=fla.name,
        by_position=[
            RigPlacement(index=1, x_pos=0, y_pos=0,
                         library_name="a", label="front"),
            RigPlacement(index=2, x_pos=100, y_pos=0, library_name="b"),
        ],
    )
    save_labels(sidecar_path_for(fla), labels)
    rc = rig_labeler.main([
        "--rig", str(fla),
        "--list",
        "--log-level", "ERROR",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "front" in out
    assert "a" in out
    assert "b" in out


def test_list_missing_sidecar_returns_2(tmp_path):
    fla = _build_minimal_fla(tmp_path, [("a", 0)])
    rc = rig_labeler.main([
        "--rig", str(fla),
        "--list",
        "--log-level", "ERROR",
    ])
    assert rc == 2


# ─── argparse modes ──────────────────────────────────────────────


def test_cli_requires_exactly_one_mode(tmp_path):
    """argparse mutually-exclusive group must reject 0 or 2 modes."""
    fla = _build_minimal_fla(tmp_path, [("a", 0)])
    with pytest.raises(SystemExit):
        rig_labeler.main(["--rig", str(fla)])
    with pytest.raises(SystemExit):
        rig_labeler.main(["--rig", str(fla), "--init", "--verify"])
