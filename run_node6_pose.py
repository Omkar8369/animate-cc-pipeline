"""Repo-root wrapper for Node 6 pose estimation.

Inserts the repo root onto sys.path so the embedded Python (which
ignores PYTHONPATH per its python313._pth) can import the package.
Same pattern as the prior `animatic-refinement` project's
run_node*.py wrappers.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from animate_cc_pipeline.pipeline.cli_node6_pose import main

if __name__ == "__main__":
    sys.exit(main())
