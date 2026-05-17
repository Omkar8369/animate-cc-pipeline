"""Rig labeler (Phase 3o-adapter) — sidecar generator + verifier.

Production rigs from the rigger have obfuscated symbol names. This
tool builds a `<rig>.labels.json` sidecar mapping operator-friendly
angle labels (`front`, `side_l`, ...) to the actual library symbol
names. The pipeline reads the sidecar to resolve identities at
shot-assembly time.

Workflow:

    # 1. Initialize a placeholder sidecar from the .fla
    <python> tools/phase3/rig_labeler.py --rig <path.fla> \\
        --character JETHALAL --init

    # 2. Open the placeholder file in your editor + the matching
    #    PNG turnaround sheet in your image viewer. Fill in the
    #    `label` field on each `by_position` entry, using values
    #    from STANDARD_ANGLE_LABELS (front, front_3q_l, side_l,
    #    back, back_3q_l, etc.). Leave non-character entries as
    #    FILL_ME_IN — they'll be ignored.

    # 3. Verify
    <python> tools/phase3/rig_labeler.py --rig <path.fla> --verify

    # 4. (Optional) List the resolved labels
    <python> tools/phase3/rig_labeler.py --rig <path.fla> --list

Exit codes:
  0  success (init OK, verify passed, list printed)
  1  verify FAILED (placeholders remain)
  2  setup error (missing .fla, can't write, etc.)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from animate_cc_pipeline.pipeline.rig_labels import (
    PLACEHOLDER,
    STANDARD_ANGLE_LABELS,
    initialize_labels_for_rig,
    load_labels,
    save_labels,
    sidecar_path_for,
)


logger = logging.getLogger("rig_labeler")


def _cmd_init(args: argparse.Namespace) -> int:
    if not args.character:
        logger.error("--character is required for --init")
        return 2
    if not args.rig.exists():
        logger.error("rig .fla not found: %s", args.rig)
        return 2

    sidecar = args.sidecar or sidecar_path_for(args.rig)
    if sidecar.exists() and not args.force:
        logger.error(
            "sidecar already exists: %s (use --force to overwrite)", sidecar,
        )
        return 2

    try:
        labels = initialize_labels_for_rig(args.rig, character=args.character)
    except Exception as exc:
        logger.error("could not parse rig .fla %s: %s", args.rig, exc)
        return 2

    save_labels(sidecar, labels)
    print(f"wrote {sidecar}")
    print(f"  character: {args.character}")
    print(f"  placements: {len(labels.by_position)}")
    print()
    print(
        "Next step: open the sidecar in a text editor + the matching "
        "PNG turnaround sheet (next to the .fla, named "
        "<character>_TURNAROUND_FINAL.png). For each by_position "
        "entry, set `label` to one of:"
    )
    for lbl in STANDARD_ANGLE_LABELS:
        print(f"  - {lbl}")
    print(
        "Entries that are not character poses (e.g. shadow layers, "
        f"reference photos) can be left as {PLACEHOLDER!r} — they "
        "will be skipped at resolution time."
    )
    print()
    print(f"Then run: --rig <path> --verify")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    sidecar = args.sidecar or sidecar_path_for(args.rig)
    if not sidecar.exists():
        logger.error("sidecar not found: %s; run --init first", sidecar)
        return 2

    try:
        labels = load_labels(sidecar)
    except Exception as exc:
        logger.error("could not parse sidecar %s: %s", sidecar, exc)
        return 2

    # Cross-check: rig filename in sidecar should match the .fla
    if args.rig and labels.rig_fla_filename != args.rig.name:
        print(
            f"WARNING: sidecar.rig_fla_filename={labels.rig_fla_filename!r} "
            f"but --rig basename={args.rig.name!r}"
        )

    filled = labels.filled_count()
    total = len(labels.by_position)
    print(f"sidecar: {sidecar}")
    print(f"character: {labels.character}")
    print(f"filled: {filled} / {total} placements")
    print(f"labels map: {len(labels.labels)} entries")

    if labels.labels:
        print()
        print("Resolved labels:")
        for label, lib_name in sorted(labels.labels.items()):
            print(f"  {label:20s} -> {lib_name!r}")

    # Verify policy:
    #   - Empty labels map → FAIL (operator hasn't filled anything in)
    #   - All placements left as PLACEHOLDER but some marked as
    #     "ignore" via the standard label set → still requires at
    #     least one filled-in label, otherwise the rig is unusable.
    if not labels.labels:
        print()
        print("FAIL: no labels filled in. Edit the sidecar JSON and re-run.")
        return 1

    print()
    print("OK")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    sidecar = args.sidecar or sidecar_path_for(args.rig)
    if not sidecar.exists():
        logger.error("sidecar not found: %s; run --init first", sidecar)
        return 2
    try:
        labels = load_labels(sidecar)
    except Exception as exc:
        logger.error("could not parse sidecar %s: %s", sidecar, exc)
        return 2

    print(f"character: {labels.character}")
    print(f"placements (left-to-right):")
    for p in labels.by_position:
        marker = "OK  " if p.label != PLACEHOLDER else "----"
        print(
            f"  [{marker}] idx={p.index:2d}  x={p.x_pos:8.1f}  "
            f"label={p.label!r:20s}  library={p.library_name!r}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rig_labeler",
        description=(
            "Build + verify rig label sidecars (Phase 3o-adapter)."
        ),
    )
    parser.add_argument(
        "--rig", type=Path, required=True,
        help="Path to the rig .fla.",
    )
    parser.add_argument(
        "--sidecar", type=Path, default=None,
        help="Override the sidecar path (default: <rig>.labels.json).",
    )
    parser.add_argument(
        "--character", type=str, default=None,
        help="Character display name (required for --init).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing sidecar when running --init.",
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--init", action="store_true",
        help="Generate a placeholder sidecar from the .fla.",
    )
    mode.add_argument(
        "--verify", action="store_true",
        help="Check the sidecar has at least one filled-in label.",
    )
    mode.add_argument(
        "--list", action="store_true",
        help="Print the sidecar's placements + labels.",
    )

    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARN", "ERROR"],
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if args.init:
        return _cmd_init(args)
    if args.verify:
        return _cmd_verify(args)
    if args.list:
        return _cmd_list(args)
    return 2  # unreachable; argparse enforces mutually-exclusive


if __name__ == "__main__":
    sys.exit(main())
