"""Rig label sidecars (Phase 3o-adapter).

The production rig .fla files we received from the rigger have
obfuscated library symbol names (e.g. `fgbfgfgn`, `DGHGHENHGE`) —
the rigger built the file without following RIG_SPEC_v1's naming
convention. Rather than rename hundreds of symbols by hand, we
ship a tiny sidecar JSON file alongside each rig that maps
human-readable angle labels (`front`, `side_l`, `back`) to the
real library symbol names.

The sidecar is `<rig_basename>.labels.json`. Example:

    {
      "schemaVersion": 1,
      "character": "JETHALAL",
      "rig_fla_filename": "JETHALAL_Turnaround_FINAL.fla",
      "labels": {
        "front":      "fgbfgfgn",
        "front_3q_r": "axadfvdfv",
        "side_r":     "fhnfhnhnSDVSDAV",
        ...
      },
      "by_position": [
        {"index": 1, "x_pos": 366.45, "library_name": "fgbfgfgn", "label": "front"},
        ...
      ]
    }

`labels` is the consumer-facing map (used by import_character_rig).
`by_position` is operator-facing: the placed-on-main-timeline list
sorted left-to-right, so operators can fill in labels using the
PNG turnaround sheet as visual reference.

Why .fla can be parsed without Animate:
    Adobe Animate's `.fla` files (CS5+ XFL format) are zip archives
    containing XML. `DOMDocument.xml` describes the main timeline;
    each placed symbol's `libraryItemName` + `Matrix tx/ty` is
    directly readable. No JSFL or Animate.exe required.

The Adobe zip format includes a 54-byte trailing chunk that
generic `unzip` complains about but Python's stdlib `zipfile`
handles fine.
"""

from __future__ import annotations

import io
import json
import logging
import struct
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


logger = logging.getLogger("rig_labels")


# ─── Schemas ──────────────────────────────────────────────────────


# Conventional turnaround labels operators will use. Not enforced by
# the schema — the labels dict can hold any key — but documented here
# so the labeler CLI can prompt with sensible defaults.
STANDARD_ANGLE_LABELS = (
    "front",
    "front_3q_l",  # 3/4 facing camera, body angled to operator's right
    "front_3q_r",
    "side_l",
    "side_r",
    "back",
    "back_3q_l",
    "back_3q_r",
)


PLACEHOLDER = "FILL_ME_IN"


class RigPlacement(BaseModel):
    """One Graphic Symbol placed on the rig .fla's main timeline.

    Sorted left-to-right by `x_pos` so operators can fill in labels
    by looking at the rigger's PNG turnaround sheet from left to
    right.
    """
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)  # 1-indexed left-to-right
    x_pos: float
    y_pos: float
    library_name: str
    """The actual obfuscated symbol name in the .fla library."""
    label: str = PLACEHOLDER
    """Operator-supplied semantic label (e.g. "front", "side_r").
    PLACEHOLDER means the operator hasn't filled it in yet."""


class RigLabels(BaseModel):
    """Sidecar contents — one file per .fla rig."""
    model_config = ConfigDict(extra="forbid")

    schemaVersion: int = Field(default=1, ge=1)
    character: str
    """The character's display name (e.g. 'JETHALAL'). Operator-set."""
    rig_fla_filename: str
    """The .fla filename (no path). Used to detect rig/sidecar
    mismatch."""
    labels: dict[str, str] = Field(default_factory=dict)
    """`{label_name: library_symbol_name}` — consumer-facing map.
    Derived from `by_position` entries whose label is not
    PLACEHOLDER."""
    by_position: list[RigPlacement] = Field(default_factory=list)
    """The full main-timeline placement list, sorted left-to-right."""

    def resolve(self, identity_or_label: str) -> Optional[str]:
        """Resolve a name to a library symbol.

        If `identity_or_label` matches a label key, return the
        mapped library_name. Otherwise return it unchanged —
        callers may pass a direct library symbol name (advanced
        use) and we just pass it through.

        Returns None if the input doesn't match any label and
        doesn't appear in by_position either (caller should treat
        as an unrecognized identity).
        """
        if identity_or_label in self.labels:
            return self.labels[identity_or_label]
        # Direct library name passthrough — only allow if it's
        # actually in the rig's placement list.
        for p in self.by_position:
            if p.library_name == identity_or_label:
                return identity_or_label
        return None

    def filled_count(self) -> int:
        """Number of placements whose label is filled in (not PLACEHOLDER)."""
        return sum(1 for p in self.by_position if p.label != PLACEHOLDER)


# ─── .fla parsing ─────────────────────────────────────────────────


# Adobe's XFL XML namespace
_XFL_NS = "http://ns.adobe.com/xfl/2008/"


def _strip_ns(tag: str) -> str:
    """ET element tags include `{ns}name`; strip the namespace."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _read_fla_zip_lenient(fla_path: Path) -> zipfile.ZipFile:
    """Open a .fla as zip, working around Adobe's non-standard EOCD.

    Adobe Animate writes XFL .fla files whose End-Of-Central-Directory
    record reports a `central directory size` field that's 54 bytes
    larger than the actual CD bytes. Python's stdlib `zipfile`
    refuses to open such files with `BadZipFile: Bad magic number for
    central directory`. The CD itself is fine — only the size field
    is bogus.

    We patch the EOCD's `cd_size` field in memory (cd_size :=
    eocd_offset - cd_offset) before handing the bytes to zipfile.
    """
    data = fla_path.read_bytes()
    eocd_sig = b"PK\x05\x06"
    eocd_idx = data.rfind(eocd_sig)
    if eocd_idx < 0:
        raise ValueError(f"no EOCD signature in {fla_path}")

    # EOCD layout (22 bytes minimum):
    #   off  0: signature (4)        — PK\x05\x06
    #   off  4: disk number (2)
    #   off  6: disk where CD starts (2)
    #   off  8: CD records on this disk (2)
    #   off 10: total CD records (2)
    #   off 12: CD size in bytes (4)
    #   off 16: CD offset (4)
    #   off 20: comment length (2)
    cd_size_field_off = eocd_idx + 12
    cd_offset_field_off = eocd_idx + 16
    cd_offset = struct.unpack_from("<I", data, cd_offset_field_off)[0]
    true_cd_size = eocd_idx - cd_offset
    if true_cd_size < 0:
        raise ValueError(
            f"computed negative CD size for {fla_path} — file may be truncated"
        )

    patched = bytearray(data)
    struct.pack_into("<I", patched, cd_size_field_off, true_cd_size)

    return zipfile.ZipFile(io.BytesIO(bytes(patched)))


def extract_placements_from_fla(fla_path: Path) -> list[RigPlacement]:
    """Parse a .fla zip archive's DOMDocument.xml and return the
    main-timeline Graphic Symbol placements sorted left-to-right.

    Raises FileNotFoundError if the .fla isn't a valid zip or
    doesn't contain DOMDocument.xml.
    """
    if not fla_path.exists():
        raise FileNotFoundError(f"rig .fla not found: {fla_path}")

    try:
        zf = _read_fla_zip_lenient(fla_path)
    except zipfile.BadZipFile as exc:
        raise ValueError(
            f".fla is not a valid zip archive (not XFL format?): {fla_path}"
        ) from exc

    try:
        try:
            dom_xml_bytes = zf.read("DOMDocument.xml")
        except KeyError as exc:
            raise ValueError(
                f".fla does not contain DOMDocument.xml; not an XFL-format file? "
                f"path={fla_path}"
            ) from exc
    finally:
        zf.close()

    return _parse_dom_xml(dom_xml_bytes)


def _parse_dom_xml(dom_xml_bytes: bytes) -> list[RigPlacement]:
    """Pure parser — separable so we can unit-test against synthetic
    XML without needing a real .fla."""
    root = ET.fromstring(dom_xml_bytes)

    placements_raw: list[tuple[str, float, float]] = []
    # We iterate all DOMSymbolInstance elements anywhere under the
    # root timelines/timeline/layers/layer/frames/frame/elements
    # tree. XFL nests deeply so a recursive walk is simplest.
    for el in root.iter():
        if _strip_ns(el.tag) != "DOMSymbolInstance":
            continue
        if el.attrib.get("symbolType") != "graphic":
            continue
        library_name = el.attrib.get("libraryItemName", "")
        if not library_name:
            continue
        # Find the Matrix child to extract tx/ty
        tx: float = 0.0
        ty: float = 0.0
        for child in el.iter():
            if _strip_ns(child.tag) != "Matrix":
                continue
            tx = float(child.attrib.get("tx", 0))
            ty = float(child.attrib.get("ty", 0))
            break
        placements_raw.append((library_name, tx, ty))

    # Sort by x_pos ascending → left-to-right
    placements_raw.sort(key=lambda t: t[1])

    return [
        RigPlacement(
            index=i + 1,
            x_pos=tx,
            y_pos=ty,
            library_name=name,
        )
        for i, (name, tx, ty) in enumerate(placements_raw)
    ]


# ─── Sidecar I/O ──────────────────────────────────────────────────


def sidecar_path_for(rig_fla_path: Path) -> Path:
    """Standard sidecar location: `<rig>.labels.json` next to the .fla."""
    return rig_fla_path.with_suffix(rig_fla_path.suffix + ".labels.json")


def load_labels(sidecar_path: Path) -> RigLabels:
    """Load a sidecar from disk."""
    if not sidecar_path.exists():
        raise FileNotFoundError(f"labels sidecar not found: {sidecar_path}")
    return RigLabels.model_validate_json(sidecar_path.read_text(encoding="utf-8"))


def save_labels(sidecar_path: Path, labels: RigLabels) -> None:
    """Save a sidecar to disk, refreshing the labels map from by_position
    so the two stay in sync."""
    labels.labels = {
        p.label: p.library_name
        for p in labels.by_position
        if p.label != PLACEHOLDER
    }
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text(labels.model_dump_json(indent=2), encoding="utf-8")


def initialize_labels_for_rig(
    rig_fla_path: Path,
    character: str,
) -> RigLabels:
    """Build a fresh RigLabels with all labels as PLACEHOLDER.

    Operator fills in the by_position entries' `label` fields,
    then calls save_labels which refreshes the labels map.
    """
    placements = extract_placements_from_fla(rig_fla_path)
    return RigLabels(
        character=character,
        rig_fla_filename=rig_fla_path.name,
        by_position=placements,
        labels={},
    )


def resolve_identity_via_sidecar(
    rig_fla_path: Path,
    identity: str,
) -> tuple[str, Optional[Path]]:
    """Given a rig path + identity, resolve to the actual library
    symbol name to instantiate.

    Returns `(resolved_name, sidecar_path_used_or_None)`.

    Resolution order:
        1. If a sidecar exists at the standard location AND it has
           a label matching `identity`, use that mapping.
        2. Otherwise return `identity` unchanged — the caller will
           pass it through to JSFL, which may still succeed if the
           operator passed a direct library symbol name.

    No exceptions: callers can rely on a graceful pass-through if
    no sidecar / unmatched label.
    """
    sidecar = sidecar_path_for(rig_fla_path)
    if not sidecar.exists():
        return (identity, None)
    try:
        labels = load_labels(sidecar)
    except Exception as exc:
        logger.warning(
            "could not parse labels sidecar %s: %s; passing identity through",
            sidecar, exc,
        )
        return (identity, None)
    resolved = labels.resolve(identity)
    if resolved is None:
        # Identity didn't match any label and isn't a direct
        # library name in this rig's placements — pass through
        # anyway (the JSFL might still find it).
        return (identity, sidecar)
    return (resolved, sidecar)
