"""Auto-configure ``.claude/settings.local.json`` with this machine's
Python interpreter, so Claude Code can launch the animate-cc MCP
server.

The committed ``.claude/settings.json`` uses ``"command": "python"``
for portability across machines. On machines where ``python`` is
not on PATH (e.g., Windows operators running Adobe Animate alongside
ComfyUI portable, with no system Python install), this script
generates a local override that points ``command`` at a concrete
Python executable.

Resolution order:
  1. ``--python <path>`` CLI argument.
  2. ``ANIMATE_MCP_PYTHON`` env var.
  3. ComfyUI portable's embedded Python, if it's a sibling of this
     repo (``../ComfyUI_windows_portable/python_embeded/python.exe``
     or one directory further up).
  4. ``python`` / ``python3`` on PATH.

Usage:
    <any-python> tools/phase3/setup_local_python.py
    <any-python> tools/phase3/setup_local_python.py --python "C:/..."
    <any-python> tools/phase3/setup_local_python.py --dry-run

Exit codes:
  0 — wrote (or --dry-run printed) the local override
  1 — could not find a usable Python interpreter
  2 — provided ``--python`` path does not exist
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SETTINGS_LOCAL = REPO_ROOT / ".claude" / "settings.local.json"


def find_python() -> Optional[str]:
    """Return a usable Python interpreter path, or None if none found."""

    # 1. Env var
    env_py = os.environ.get("ANIMATE_MCP_PYTHON", "").strip()
    if env_py and Path(env_py).exists():
        return env_py

    # 2. ComfyUI embedded Python siblings (one or two directories up)
    candidates = [
        REPO_ROOT.parent / "ComfyUI_windows_portable" / "python_embeded" / "python.exe",
        REPO_ROOT.parent.parent / "ComfyUI_windows_portable" / "python_embeded" / "python.exe",
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand)

    # 3. System python on PATH
    for cmd in ("python", "python3"):
        sys_py = shutil.which(cmd)
        if sys_py:
            return sys_py

    return None


def build_config(python_path: str) -> dict:
    return {
        "_comment": (
            "Local override created by tools/phase3/setup_local_python.py. "
            "Points the animate-cc MCP server's `command` at this machine's "
            "Python interpreter. This file is gitignored and machine-specific. "
            "Re-run setup_local_python.py if Python's location changes."
        ),
        "mcpServers": {
            "animate-cc": {
                "command": python_path,
            }
        },
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Auto-configure .claude/settings.local.json for the "
            "animate-cc MCP server on this machine."
        )
    )
    parser.add_argument(
        "--python",
        help="Path to Python executable to use for the MCP server.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written; do not modify any files.",
    )
    args = parser.parse_args(argv)

    if args.python:
        python_path = Path(args.python).resolve()
        if not python_path.exists():
            print(
                f"ERROR: --python path does not exist: {python_path}",
                file=sys.stderr,
            )
            return 2
        chosen = str(python_path)
        source = "--python CLI argument"
    else:
        chosen = find_python()
        if not chosen:
            print(
                "ERROR: could not find a Python interpreter.\n"
                "Try one of:\n"
                "  1. Pass --python <full-path-to-python.exe>\n"
                "  2. Set ANIMATE_MCP_PYTHON env var\n"
                "  3. Install ComfyUI_windows_portable as a sibling of\n"
                "     this repo (its embedded Python will be detected)\n"
                "  4. Add Python to system PATH\n",
                file=sys.stderr,
            )
            return 1
        source = "auto-detection"

    config = build_config(chosen)

    print(f"Detected Python: {chosen}  (source: {source})")
    print(f"Target: {SETTINGS_LOCAL}")

    if args.dry_run:
        print("--dry-run: not writing. Would write:")
        print(json.dumps(config, indent=2))
        return 0

    SETTINGS_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_LOCAL.write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {SETTINGS_LOCAL}")
    print("animate-cc MCP server will now launch via this Python interpreter.")
    print("(File is gitignored; safe to commit nothing.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
