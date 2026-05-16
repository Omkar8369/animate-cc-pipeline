"""Node 7 CLI: assemble shots into .fla + MP4 via the MCP toolbelt.

Reads a JSON batch config file describing per-shot inputs, runs
`process_shots` over them, writes an aggregate
`animate_assembly.json` to the work directory.

Batch config schema (JSON):

    {
      "schemaVersion": 1,
      "work_dir": "C:/path/to/work",
      "shots": [
        {
          "shot_id": "shot_001",
          "fla_out_path": "C:/path/to/work/shot_001/auto.fla",
          "mp4_out_path": "C:/path/to/work/shot_001/draft.mp4",
          "animatic_mp4_path": "C:/.../shot_001.mp4",
          "background_image_path": "C:/.../bg_living_room.png",
          "audio_wav_path": "C:/.../shot_001.wav",
          "width": 1920, "height": 1080, "fps": 25,
          "characters": [
            {
              "identity": "JETHALAL",
              "rig_fla_path": "rigs/jethalal.fla",     // OR
              "placeholder_image_path": "test/jethalal.png",
              "pose_map_path": "work/shot_001/pose_map.json"
            },
            ...
          ]
        },
        ...
      ]
    }

CLI exit codes:
  0  all shots succeeded
  1  at least one shot failed (assembly report has details)
  2  unexpected error before processing began (bad config, etc.)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from .assembly_schemas import AssemblyReport, CharacterConfig, ShotConfig
from .shot_processor import process_shots


logger = logging.getLogger("cli_node7_animate")


def _parse_config(path: Path) -> list[ShotConfig]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schemaVersion") != 1:
        raise ValueError(f"batch config must have schemaVersion=1; got {raw.get('schemaVersion')!r}")
    shots = []
    for shot_raw in raw.get("shots", []):
        chars = [CharacterConfig(**c) for c in shot_raw.pop("characters", [])]
        shots.append(ShotConfig(characters=chars, **shot_raw))
    return shots


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cli_node7_animate",
        description="Assemble shots into .fla + MP4 via the MCP toolbelt.",
    )
    parser.add_argument("--config", type=Path, required=True,
                        help="Path to the batch config JSON")
    parser.add_argument("--report-out", type=Path, default=None,
                        help="Path to write the aggregate animate_assembly.json "
                             "(default: <config_dir>/animate_assembly.json)")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARN", "ERROR"])
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    try:
        shots = _parse_config(args.config)
    except Exception as exc:
        logger.error("failed to parse config %s: %s", args.config, exc)
        return 2

    if not shots:
        logger.warning("config contained no shots; nothing to do")
        return 0

    logger.info("starting batch assembly: %d shot(s)", len(shots))
    report: AssemblyReport = asyncio.run(process_shots(shots))

    # Write the report
    out_path = args.report_out or (args.config.parent / "animate_assembly.json")
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        logger.info("wrote assembly report: %s", out_path)
    except OSError as exc:
        logger.error("could not write report to %s: %s", out_path, exc)
        return 2

    logger.info(
        "batch done: %d succeeded, %d failed (of %d)",
        report.num_succeeded, report.num_failed, len(report.shots),
    )
    return 0 if report.num_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
