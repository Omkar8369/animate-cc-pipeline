"""Repo-root wrapper for camera move detection.

sys.path fixup for embedded Python — same pattern as the other
run_*.py wrappers.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from animate_cc_pipeline.pipeline.cli_camera_detector import main

if __name__ == "__main__":
    sys.exit(main())
