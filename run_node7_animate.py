"""Repo-root wrapper for Node 7 (orchestrator).

sys.path fixup for embedded Python — same pattern as run_node6_pose.py
and the prior project's run_node*.py wrappers.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from animate_cc_pipeline.pipeline.orchestrator.cli_node7_animate import main

if __name__ == "__main__":
    sys.exit(main())
