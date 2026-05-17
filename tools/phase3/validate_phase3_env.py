"""Phase 3p-docs: environment validator.

Runs a series of pre-flight checks against this machine's
configuration to confirm the pipeline can run. Used both:

  - By the operator BEFORE attempting the first end-to-end run on
    a new machine — surfaces missing deps, wrong paths, broken
    settings files.
  - In CI / smoke contexts — exit code 1 if any fatal check fails.

Each check is a small function returning a `CheckResult`. Checks
are intentionally independent: one failure does not cascade,
because a clean-machine bringup typically has multiple drift
points and you want to see ALL of them in one run instead of
fixing-and-rerunning.

Usage:
    <python> tools/phase3/validate_phase3_env.py [--strict] [--quiet]

Exit codes:
  0 — all fatal checks passed (warnings may still print)
  1 — at least one fatal check failed
  2 — internal validator bug (this shouldn't happen)

Add new checks by appending a function returning `CheckResult` to
`ALL_CHECKS` at the bottom of this file.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# sys.path fixup — same pattern as run_*.py wrappers so the validator
# can find animate_cc_pipeline.* when invoked as a standalone script
# from any working directory.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── Result schema ────────────────────────────────────────────────


@dataclass
class CheckResult:
    """One check's outcome.

    `fatal=False` means a failure is reported but does NOT cause
    the overall exit code to be 1. Used for warnings ("nice to have"
    things like a real Animate.exe path when running unit tests
    only).
    """
    name: str
    ok: bool
    message: str
    fatal: bool = True
    hint: str = ""


# ─── Individual checks ────────────────────────────────────────────


MIN_PYTHON = (3, 11)


def check_python_version() -> CheckResult:
    """The pipeline requires Python 3.11+ for pydantic v2 + modern
    typing syntax (`X | None`, etc.).
    """
    if sys.version_info >= MIN_PYTHON:
        return CheckResult(
            name="python_version",
            ok=True,
            message=f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    return CheckResult(
        name="python_version",
        ok=False,
        message=(
            f"Python {sys.version_info.major}.{sys.version_info.minor} "
            f"is below required {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+"
        ),
        hint=(
            "Use the embedded Python at "
            "ComfyUI_windows_portable/python_embeded/python.exe "
            "(3.13.x) — see CLAUDE.md."
        ),
    )


REQUIRED_MODULES = [
    "mcp",
    "pydantic",
    "numpy",
    "PIL",
    "imageio_ffmpeg",
    "cv2",  # opencv-python (camera_detector fallback uses numpy but cv2 is preferred)
]

OPTIONAL_MODULES = [
    "pytest",
    "pytest_mock",
]


def check_required_modules() -> CheckResult:
    """All modules listed in requirements.txt's "required" lines must
    import. Optional dev modules (pytest) are reported separately.
    """
    missing: list[str] = []
    for mod in REQUIRED_MODULES:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    if not missing:
        return CheckResult(
            name="required_modules",
            ok=True,
            message=f"all {len(REQUIRED_MODULES)} required modules importable",
        )
    return CheckResult(
        name="required_modules",
        ok=False,
        message=f"missing: {', '.join(missing)}",
        hint=(
            "Run: <python> -m pip install -r requirements.txt "
            "(use the embedded Python; see CLAUDE.md)."
        ),
    )


def check_optional_modules() -> CheckResult:
    """Optional modules: missing → warning, never fatal."""
    missing: list[str] = []
    for mod in OPTIONAL_MODULES:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    if not missing:
        return CheckResult(
            name="optional_modules",
            ok=True,
            message=f"all {len(OPTIONAL_MODULES)} optional modules importable",
            fatal=False,
        )
    return CheckResult(
        name="optional_modules",
        ok=False,
        message=f"missing optional: {', '.join(missing)}",
        fatal=False,
        hint="Install for full dev tooling: <python> -m pip install pytest pytest-mock",
    )


def _default_animate_exe() -> str:
    return r"C:\Program Files\Adobe\Adobe Animate 2020\Animate.exe"


def check_animate_exe() -> CheckResult:
    """The Animate.exe path must resolve to an existing file — Animate
    is the pipeline's renderer. Resolved via ANIMATE_CC_EXE env var
    or the documented default in CLAUDE.md.

    NOT fatal: validator can still smoke-test pure-Python pipeline
    modules without Animate. But the .fla / MP4 ops require it.
    """
    path_str = os.environ.get("ANIMATE_CC_EXE", _default_animate_exe())
    path = Path(path_str)
    if path.exists():
        return CheckResult(
            name="animate_exe",
            ok=True,
            message=f"found at {path}",
        )
    return CheckResult(
        name="animate_exe",
        ok=False,
        message=f"Animate.exe not found at {path}",
        fatal=False,  # pure-Python checks still pass; degrades MCP smoke
        hint=(
            "Install Adobe Animate CC 2020+ or set ANIMATE_CC_EXE env "
            "var to the correct path. Required for any .fla / MP4 work."
        ),
    )


def check_settings_local_json() -> CheckResult:
    """The .claude/settings.local.json override should exist on a
    machine where the embedded Python isn't on PATH. NOT fatal — the
    committed .claude/settings.json with `command: "python"` may
    work if a system Python is available.
    """
    target = REPO_ROOT / ".claude" / "settings.local.json"
    if target.exists():
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except Exception as exc:
            return CheckResult(
                name="settings_local_json",
                ok=False,
                message=f"file exists but is not valid JSON: {exc}",
                hint="Re-run tools/phase3/setup_local_python.py to regenerate.",
            )
        cmd = (
            data.get("mcpServers", {})
                .get("animate-cc", {})
                .get("command", "")
        )
        if cmd and Path(cmd).exists():
            return CheckResult(
                name="settings_local_json",
                ok=True,
                message=f"points at {cmd}",
            )
        return CheckResult(
            name="settings_local_json",
            ok=False,
            message=f"settings.local.json present but `command` is invalid: {cmd!r}",
            hint="Re-run tools/phase3/setup_local_python.py.",
        )
    return CheckResult(
        name="settings_local_json",
        ok=False,
        message="no .claude/settings.local.json - relying on committed settings.json",
        fatal=False,
        hint=(
            "Run: <python> tools/phase3/setup_local_python.py "
            "to write the local override pointing at this machine's "
            "Python interpreter."
        ),
    )


def check_mcp_server_imports() -> CheckResult:
    """The animate_cc_pipeline.mcp_server.server module must import
    without errors. Catches the common breakage where requirements
    drift from imports."""
    try:
        from animate_cc_pipeline.mcp_server import server  # noqa: F401
    except Exception as exc:
        return CheckResult(
            name="mcp_server_imports",
            ok=False,
            message=f"{type(exc).__name__}: {exc}",
            hint="Likely a missing dep - check `required_modules` above.",
        )
    return CheckResult(
        name="mcp_server_imports",
        ok=True,
        message="animate_cc_pipeline.mcp_server.server imports cleanly",
    )


def check_pipeline_modules_import() -> CheckResult:
    """All shipped pipeline modules must import. Catches accidental
    syntax errors / circular imports introduced by a refactor."""
    modules = [
        "animate_cc_pipeline.pipeline.schemas",
        "animate_cc_pipeline.pipeline.pose_estimator",
        "animate_cc_pipeline.pipeline.pose_to_bones",
        "animate_cc_pipeline.pipeline.camera_detector",
        "animate_cc_pipeline.pipeline.batch_runner",
        "animate_cc_pipeline.pipeline.rig_labels",  # Phase 3o-adapter
        "animate_cc_pipeline.pipeline.orchestrator.shot_processor",
        "animate_cc_pipeline.pipeline.orchestrator.assembly_schemas",
    ]
    broken: list[tuple[str, str]] = []
    for mod_name in modules:
        try:
            importlib.import_module(mod_name)
        except Exception as exc:
            broken.append((mod_name, f"{type(exc).__name__}: {exc}"))
    if not broken:
        return CheckResult(
            name="pipeline_modules_import",
            ok=True,
            message=f"all {len(modules)} pipeline modules import cleanly",
        )
    msg = "; ".join(f"{name}: {err}" for name, err in broken)
    return CheckResult(
        name="pipeline_modules_import",
        ok=False,
        message=msg,
        hint="Likely a missing dep or a recent code change with a broken import.",
    )


CANONICAL_FILES = [
    "CLAUDE.md",
    "README.md",
    "docs/PLAN.md",
    "docs/PHASE_3_ROADMAP.md",
    "animate_cc_pipeline/README.md",
    "requirements.txt",
]


def check_canonical_files_exist() -> CheckResult:
    """All six canonical files must exist. Drift between them is a
    separate (manual) cross-check; this only catches "someone
    deleted a file" regressions."""
    missing = [name for name in CANONICAL_FILES if not (REPO_ROOT / name).exists()]
    if not missing:
        return CheckResult(
            name="canonical_files_exist",
            ok=True,
            message=f"all {len(CANONICAL_FILES)} canonical files present",
        )
    return CheckResult(
        name="canonical_files_exist",
        ok=False,
        message=f"missing: {', '.join(missing)}",
        hint="See CLAUDE.md for the canonical file list.",
    )


def check_run_wrappers_exist() -> CheckResult:
    """The repo-root run_*.py wrappers must exist (each phase that
    ships a CLI also ships a repo-root wrapper).

    Why this matters: operators paste the wrapper paths from CLAUDE.md
    quick-start; a missing wrapper means a copy-paste'd command 404s.
    """
    expected = [
        "run_camera_detect.py",
        "run_batch.py",
    ]
    missing = [name for name in expected if not (REPO_ROOT / name).exists()]
    if not missing:
        return CheckResult(
            name="run_wrappers_exist",
            ok=True,
            message=f"all {len(expected)} run wrappers present",
        )
    return CheckResult(
        name="run_wrappers_exist",
        ok=False,
        message=f"missing: {', '.join(missing)}",
        hint="Each phase that ships a CLI also ships a repo-root run_*.py wrapper.",
    )


def check_jsfl_templates_present() -> CheckResult:
    """Each shipped MCP tool that calls JSFL ships a template under
    animate_cc_pipeline/mcp_server/jsfl_templates/. This check
    enforces that the file inventory hasn't silently regressed."""
    expected = [
        "create_doc.jsfl",
        "save_doc.jsfl",
        "import_image.jsfl",
        "import_video.jsfl",
        "import_character_rig.jsfl",  # Phase 3o-code
        "place_symbol_instance.jsfl",
        "set_instance_position.jsfl",
        "set_instance_rotation.jsfl",
        "set_instance_scale.jsfl",
        "insert_keyframe.jsfl",
        "insert_blank_keyframe.jsfl",
        "remove_keyframe.jsfl",
        "get_keyframes.jsfl",
        "set_graphic_first_frame.jsfl",
        "get_graphic_first_frame.jsfl",
        "dump_rig_structure.jsfl",
        "add_classic_tween.jsfl",
        "add_motion_tween.jsfl",
        "set_easing.jsfl",
        "import_audio.jsfl",
        "set_switch_state.jsfl",
        "apply_auto_lipsync.jsfl",
        "set_camera_position.jsfl",
        "export_png_sequence.jsfl",
    ]
    templates_dir = REPO_ROOT / "animate_cc_pipeline" / "mcp_server" / "jsfl_templates"
    missing = [name for name in expected if not (templates_dir / name).exists()]
    if not missing:
        return CheckResult(
            name="jsfl_templates_present",
            ok=True,
            message=f"all {len(expected)} JSFL templates present",
        )
    return CheckResult(
        name="jsfl_templates_present",
        ok=False,
        message=f"missing: {', '.join(missing)}",
        hint="A phase shipped without its JSFL template - check the most recent commit.",
    )


# ─── Registry + runner ────────────────────────────────────────────


ALL_CHECKS: list[Callable[[], CheckResult]] = [
    check_python_version,
    check_required_modules,
    check_optional_modules,
    check_animate_exe,
    check_settings_local_json,
    check_canonical_files_exist,
    check_run_wrappers_exist,
    check_jsfl_templates_present,
    check_mcp_server_imports,
    check_pipeline_modules_import,
]


def run_all_checks() -> list[CheckResult]:
    """Run every registered check. Each check is wrapped so a buggy
    check function never aborts the whole validator."""
    results: list[CheckResult] = []
    for check in ALL_CHECKS:
        try:
            results.append(check())
        except Exception as exc:
            # A check function itself crashed — that's our bug.
            results.append(CheckResult(
                name=getattr(check, "__name__", "<unknown>"),
                ok=False,
                message=f"check function itself crashed: {type(exc).__name__}: {exc}",
                hint="Validator bug - file an issue or fix the check function.",
            ))
    return results


# ─── CLI ──────────────────────────────────────────────────────────


def format_results(results: list[CheckResult], quiet: bool = False) -> str:
    """Build a human-readable summary."""
    lines = []
    width = max((len(r.name) for r in results), default=10)
    for r in results:
        status = "OK  " if r.ok else "FAIL"
        if not r.fatal and not r.ok:
            status = "WARN"
        line = f"  [{status}] {r.name.ljust(width)}  {r.message}"
        lines.append(line)
        if not r.ok and r.hint and not quiet:
            lines.append(f"          hint: {r.hint}")
    fatal_failures = [r for r in results if not r.ok and r.fatal]
    warns = [r for r in results if not r.ok and not r.fatal]
    summary = (
        f"\nSummary: {sum(1 for r in results if r.ok)} ok, "
        f"{len(warns)} warning(s), {len(fatal_failures)} fatal failure(s)"
    )
    lines.append(summary)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="validate_phase3_env",
        description=(
            "Run pre-flight checks against this machine's pipeline "
            "configuration. Exit 0 if all fatal checks pass."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Promote warnings to fatal failures (exit 1 even on warns).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-check hints (keep the per-line status only).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of human-readable output.",
    )
    args = parser.parse_args(argv)

    results = run_all_checks()

    if args.json:
        payload = {
            "results": [
                {"name": r.name, "ok": r.ok, "message": r.message,
                 "fatal": r.fatal, "hint": r.hint}
                for r in results
            ],
            "num_ok": sum(1 for r in results if r.ok),
            "num_warn": sum(1 for r in results if not r.ok and not r.fatal),
            "num_fatal": sum(1 for r in results if not r.ok and r.fatal),
        }
        print(json.dumps(payload, indent=2))
    else:
        print(format_results(results, quiet=args.quiet))

    fatal_failures = [r for r in results if not r.ok and r.fatal]
    if args.strict:
        # Promote warnings to fatal
        fatal_failures = [r for r in results if not r.ok]
    return 0 if not fatal_failures else 1


if __name__ == "__main__":
    sys.exit(main())
