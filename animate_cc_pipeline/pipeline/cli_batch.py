"""Phase 3n CLI: production batch driver.

Wraps `batch_runner.run_batch` with the standard CLI affordances
operators expect (config-file ingestion, exit codes, logging
verbosity, JSONL progress).

Usage:
    python -m animate_cc_pipeline.pipeline.cli_batch \\
        --config batch_config.json \\
        --report-out batch_report.json \\
        --jsonl batch_progress.jsonl \\
        --retry-count 2

The batch config schema is the same as cli_node7_animate's, plus the
new (optional) per-shot `camera_moves_path` field (Phase 3m → 3n
integration):

    {
      "schemaVersion": 1,
      "shots": [
        {
          "shot_id": "shot_001",
          "fla_out_path": "...",
          "mp4_out_path": "...",
          "animatic_mp4_path": "...",
          "background_image_path": "...",
          "audio_wav_path": "...",
          "camera_moves_path": "...",
          "width": 1920, "height": 1080, "fps": 25,
          "characters": [...]
        },
        ...
      ]
    }

Exit codes:
  0  all shots succeeded (possibly after retries)
  1  at least one shot failed after retries
  2  setup error (bad config, can't write report, etc.)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .batch_runner import BatchReport, run_batch_sync
from .orchestrator.assembly_schemas import CharacterConfig, ShotConfig


logger = logging.getLogger("cli_batch")


def _parse_config(path: Path) -> list[ShotConfig]:
    """Parse the batch config JSON into a list of ShotConfig.

    Reused (with the same shape) by Phase 3l's cli_node7_animate, with
    the difference that ShotConfig now accepts the optional
    `camera_moves_path` field.
    """
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schemaVersion") != 1:
        raise ValueError(
            f"batch config must have schemaVersion=1; got {raw.get('schemaVersion')!r}"
        )
    shots: list[ShotConfig] = []
    for shot_raw in raw.get("shots", []):
        shot_raw = dict(shot_raw)  # don't mutate caller's structure
        chars = [CharacterConfig(**c) for c in shot_raw.pop("characters", [])]
        shots.append(ShotConfig(characters=chars, **shot_raw))
    return shots


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cli_batch",
        description="Phase 3n production batch driver — retries + JSONL progress.",
    )
    parser.add_argument("--config", type=Path, required=True,
                        help="Path to the batch config JSON")
    parser.add_argument("--report-out", type=Path, default=None,
                        help="Path to write the aggregate batch_report.json "
                             "(default: <config_dir>/batch_report.json)")
    parser.add_argument("--jsonl", type=Path, default=None,
                        help="Path to append per-attempt BatchProgress events. "
                             "Default: <config_dir>/batch_progress.jsonl")
    parser.add_argument("--retry-count", type=int, default=2,
                        help="Max retries per shot (default 2 = up to 3 attempts)")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARN", "ERROR"])
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if args.retry_count < 0:
        logger.error("--retry-count must be >= 0; got %d", args.retry_count)
        return 2

    try:
        shots = _parse_config(args.config)
    except Exception as exc:
        logger.error("failed to parse config %s: %s", args.config, exc)
        return 2

    if not shots:
        logger.warning("config contained no shots; nothing to do")
        return 0

    report_out = args.report_out or (args.config.parent / "batch_report.json")
    jsonl_path = args.jsonl or (args.config.parent / "batch_progress.jsonl")

    logger.info(
        "starting batch: %d shot(s), retry_count=%d, jsonl=%s",
        len(shots), args.retry_count, jsonl_path,
    )

    report: BatchReport = run_batch_sync(
        shots,
        retry_count=args.retry_count,
        jsonl_path=jsonl_path,
    )

    try:
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        logger.info("wrote batch report: %s", report_out)
    except OSError as exc:
        logger.error("could not write report to %s: %s", report_out, exc)
        return 2

    logger.info(
        "batch done: %d succeeded, %d failed (of %d), total attempts=%d",
        report.num_succeeded, report.num_failed, report.num_shots, report.total_attempts,
    )
    return 0 if report.num_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
