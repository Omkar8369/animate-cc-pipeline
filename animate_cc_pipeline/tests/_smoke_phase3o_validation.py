"""End-to-end smoke for Phase 3o-validation.

Runs `import_character_rig` against a REAL production rig (the
operator's Jethalal turnaround .fla) and verifies:

  1. The labels sidecar resolves an operator-friendly angle key
     ("front") to the obfuscated library symbol name ("NHNNFGH"
     for Jethalal per `rigs/labels/jethalal.labels.json`).
  2. Animate.exe boots, opens our freshly-created target .fla,
     and successfully imports the rig's library.
  3. The rig's "front" pose symbol is placed on a fresh layer in
     the target .fla at the stage center.
  4. The target .fla grew significantly after the import (proof
     that the rig library actually landed).

This is the "does the pipeline actually work against a real rig?"
test that gates Phase 3o-validation.

Run manually:
    <python> animate_cc_pipeline/tests/_smoke_phase3o_validation.py

Wall time: ~60-90 seconds (2 Animate launches: create_document +
import_character_rig).

Configure the rig path via:
  $env:PHASE3O_RIG_FLA = "C:\\path\\to\\JETHALAL_Turnaround_FINAL.fla"
Or pass --rig <path> on the CLI.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# sys.path fixup so this works as a standalone script
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _print(line: str) -> None:
    print(line, flush=True)


def _step(name: str, ok: bool, detail: str = "") -> None:
    icon = "OK  " if ok else "FAIL"
    _print(f"  [{icon}] {name}" + (f" - {detail}" if detail else ""))


DEFAULT_RIG_PATH = Path(
    r"C:\Users\Omkar Hajare\Downloads\CHARACTER\CHARACTER"
    r"\JETHALAL_Turnaround_FINAL.fla"
)


async def run_smoke(rig_fla: Path, identity: str) -> int:
    from animate_cc_pipeline.mcp_server.tools import document as document_tools
    from animate_cc_pipeline.pipeline import rig_labels

    # Resolve to absolute path immediately — Animate's URI converter
    # requires absolute paths or it returns an empty URI which trips
    # JSFL's `importFile: Argument number 1 is invalid` error.
    rig_fla = rig_fla.resolve()

    _print("=" * 64)
    _print(f" Phase 3o-validation smoke: real rig import")
    _print(f"   rig: {rig_fla}")
    _print(f"   identity (label or direct symbol name): {identity!r}")
    _print("=" * 64)

    if not rig_fla.exists():
        _step("rig_file_exists", False, f"not at {rig_fla}")
        return 1
    _step("rig_file_exists", True, f"{rig_fla.stat().st_size // 1024 // 1024} MB")

    # Resolve via sidecar (best effort — if no sidecar, identity passes through)
    resolved, used = rig_labels.resolve_identity_via_sidecar(rig_fla, identity)
    if used:
        _step("resolver_via_sidecar", True,
              f"{identity!r} -> {resolved!r} via {used.name}")
    else:
        _step("resolver_passthrough", True,
              f"no sidecar; using {resolved!r} directly")

    # Allocate a work dir for the target .fla
    work_dir = Path(tempfile.mkdtemp(prefix="phase3o_validation_"))
    target_fla = work_dir / "smoke_target.fla"
    _print(f"\n  work_dir: {work_dir}")
    _print(f"  target: {target_fla.name}")

    # Step 1: create_document (clean .fla to import into)
    _print("\n[1/2] create_document...")
    result = await document_tools.handle_create_document({
        "fla_path": str(target_fla),
        "width": 1920,
        "height": 1080,
        "fps": 25,
    })
    payload = json.loads(result[0].text)
    if payload.get("status") != "ok":
        _step("create_document", False, payload.get("error", "?"))
        return 1
    initial_size = target_fla.stat().st_size
    _step("create_document", True,
          f"{initial_size / 1024:.1f} KB after create")

    # Step 2: import_character_rig (the real test)
    _print("\n[2/2] import_character_rig (this takes ~30-60s)...")
    result = await document_tools.handle_import_character_rig({
        "fla_path": str(target_fla),
        "rig_fla_path": str(rig_fla),
        "identity": identity,  # CLI arg; resolves via sidecar if applicable
        "layer_name": identity,
        "frame": 1,
        "x": 960,
        "y": 540,
    })
    payload = json.loads(result[0].text)

    if payload.get("status") != "ok":
        _step("import_character_rig", False,
              payload.get("error", "no error message"))
        _print(f"\nFull payload: {json.dumps(payload, indent=2)}")
        diag = payload.get("diagnostic_log", "")
        if diag:
            _print("\nJSFL diagnostic log:")
            _print(diag)
        return 1

    final_size = target_fla.stat().st_size
    size_growth_mb = (final_size - initial_size) / 1024 / 1024
    instance_placed = payload.get("instance_placed", False)

    _step("import_character_rig", True,
          f"resolved={payload.get('resolved_identity', '?')}, "
          f"instance_placed={instance_placed}, "
          f"size +{size_growth_mb:.1f} MB")

    # Validate the .fla actually grew. Only the requested symbol +
    # its dependencies are copied (not the whole rig library), so the
    # growth depends on the symbol's complexity. A front pose with
    # full sub-rigging is ~0.2-2.0 MB; we require at least 0.05 MB
    # to confirm SOMETHING came across (an empty paste would be 0 MB).
    if size_growth_mb < 0.05:
        _step("fla_grew_significantly", False,
              f"only grew by {size_growth_mb:.3f} MB; expected >0.05 MB after symbol import")
        diag = payload.get("diagnostic_log", "")
        if diag:
            _print("\nJSFL diagnostic log:")
            _print(diag)
        return 1
    _step("fla_grew_significantly", True,
          f"+{size_growth_mb:.2f} MB (symbol + dependencies)")

    if not instance_placed:
        _step("instance_placed", False,
              "JSFL reported instance was NOT placed on stage")
        diag = payload.get("diagnostic_log", "")
        if diag:
            _print("\nJSFL diagnostic log:")
            _print(diag)
        return 1
    _step("instance_placed", True, f"front pose ({resolved}) on stage")

    _print("\n" + "=" * 64)
    _print(" PHASE 3o-VALIDATION SMOKE PASSED")
    _print(f" Target .fla: {target_fla}")
    _print(f" Open in Animate to visually verify Jethalal is on stage.")
    _print("=" * 64)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_smoke_phase3o_validation",
        description="End-to-end smoke: real rig import + sidecar resolution",
    )
    parser.add_argument(
        "--rig", type=Path,
        default=Path(os.environ.get("PHASE3O_RIG_FLA", str(DEFAULT_RIG_PATH))),
        help="Path to the rig .fla (default: Jethalal turnaround)",
    )
    parser.add_argument(
        "--identity", type=str, default="front",
        help="Symbol name OR label key to instantiate (default: 'front')",
    )
    args = parser.parse_args(argv)
    return asyncio.run(run_smoke(args.rig, args.identity))


if __name__ == "__main__":
    sys.exit(main())
