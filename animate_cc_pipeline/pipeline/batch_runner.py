"""Production batch driver (Phase 3n).

Sits on top of `orchestrator.process_shot` and adds the three things
a production run needs that the bare orchestrator doesn't:

  1. Retry policy — JSFL is flaky on the embedded Animate process,
     so an individual shot may fail spuriously. We retry up to
     `retry_count` times before declaring the shot failed.

  2. Structured JSONL progress log — every attempt writes one line
     with `shot_id`, `attempt`, `status`, `elapsed_seconds`, and
     selected ShotAssembly fields. Operators tail this file during
     long batches and dashboards parse it after.

  3. Aggregate `BatchReport` — schema-versioned, includes per-shot
     ShotAssembly + roll-up counters. This is the artifact that
     gets handed off to the next stage (Phase 3p documentation or
     a downstream review tool).

Design constraints:
  - `run_batch` is async and never raises (failures land in the report).
  - JSONL writes are appended one-at-a-time; if the process dies
    mid-batch the file still parses up to the last completed line.
  - `BatchProgress` events are written even when a retry succeeds —
    operators want to see the retry history.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .orchestrator.assembly_schemas import AssemblyReport, ShotAssembly, ShotConfig
from .orchestrator.shot_processor import process_shot
from .pose_to_bones import RigSpec


logger = logging.getLogger("batch_runner")


# ─── Schemas ──────────────────────────────────────────────────────


class BatchProgress(BaseModel):
    """One line in the JSONL progress log — one attempt at one shot.

    `status` is the outcome of THIS attempt:
      - "succeeded": process_shot returned success=True
      - "failed":    process_shot returned success=False; retry pending or exhausted
      - "retrying":  failed but more attempts remain
      - "exhausted": failed and retry budget is gone
    """
    model_config = ConfigDict(extra="forbid")

    timestamp: str  # ISO-8601 UTC
    shot_id: str
    attempt: int = Field(ge=1)
    max_attempts: int = Field(ge=1)
    status: Literal["succeeded", "failed", "retrying", "exhausted"]
    elapsed_seconds: float = 0.0
    keyposes_processed: int = 0
    characters_assembled: int = 0
    warnings_count: int = 0
    note: str = ""


class BatchReport(BaseModel):
    """Top-level aggregate report from a batch run."""
    model_config = ConfigDict(extra="forbid")

    schemaVersion: int = Field(default=1, ge=1)
    started_at: str  # ISO-8601 UTC
    finished_at: Optional[str] = None
    retry_count: int = Field(ge=0)
    total_attempts: int = Field(default=0, ge=0)
    """Sum of attempts across all shots — useful for measuring flakiness."""
    shots: list[ShotAssembly] = Field(default_factory=list)
    jsonl_path: Optional[str] = None

    @property
    def num_shots(self) -> int:
        return len(self.shots)

    @property
    def num_succeeded(self) -> int:
        return sum(1 for s in self.shots if s.success)

    @property
    def num_failed(self) -> int:
        return sum(1 for s in self.shots if not s.success)


# ─── Internals ────────────────────────────────────────────────────


def _now_iso() -> str:
    """ISO-8601 UTC timestamp with 'Z' suffix — friendlier to grep."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _append_jsonl(path: Optional[Path], event: BatchProgress) -> None:
    """Append one BatchProgress event as a single JSON line.

    No-op if path is None. Failures are logged but never raised — a
    misbehaving filesystem should not bring down the whole batch.
    """
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(event.model_dump_json())
            fh.write("\n")
    except OSError as exc:
        logger.warning("could not append progress event to %s: %s", path, exc)


def _progress(
    shot_id: str,
    attempt: int,
    max_attempts: int,
    status: str,
    assembly: Optional[ShotAssembly],
    note: str = "",
) -> BatchProgress:
    if assembly is None:
        return BatchProgress(
            timestamp=_now_iso(),
            shot_id=shot_id,
            attempt=attempt,
            max_attempts=max_attempts,
            status=status,  # type: ignore[arg-type]
            note=note,
        )
    return BatchProgress(
        timestamp=_now_iso(),
        shot_id=shot_id,
        attempt=attempt,
        max_attempts=max_attempts,
        status=status,  # type: ignore[arg-type]
        elapsed_seconds=round(assembly.total_elapsed_seconds, 2),
        keyposes_processed=assembly.keyposes_processed,
        characters_assembled=assembly.characters_assembled,
        warnings_count=len(assembly.warnings),
        note=note,
    )


# ─── Public API ───────────────────────────────────────────────────


async def run_batch(
    shots: list[ShotConfig],
    *,
    retry_count: int = 2,
    jsonl_path: Optional[Path] = None,
    rig_spec: Optional[RigSpec] = None,
) -> BatchReport:
    """Run a batch of shots with retry + progress logging.

    Args:
        shots: per-shot configs.
        retry_count: max RETRIES per shot (so a shot is attempted up
                     to retry_count+1 times). Default 2 (= 3 attempts).
        jsonl_path: if set, append a BatchProgress JSON line for
                    every attempt (including retries).
        rig_spec: forwarded to process_shot.

    Returns: BatchReport with final ShotAssembly per shot.
    """
    if retry_count < 0:
        raise ValueError(f"retry_count must be >= 0; got {retry_count}")

    max_attempts = retry_count + 1
    report = BatchReport(
        started_at=_now_iso(),
        retry_count=retry_count,
        jsonl_path=str(jsonl_path) if jsonl_path else None,
    )

    for cfg in shots:
        final_assembly: Optional[ShotAssembly] = None
        for attempt in range(1, max_attempts + 1):
            logger.info(
                "shot %s: attempt %d/%d", cfg.shot_id, attempt, max_attempts,
            )
            try:
                assembly = await process_shot(cfg, rig_spec)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("shot %s: unexpected exception: %s", cfg.shot_id, exc)
                assembly = ShotAssembly(
                    shot_id=cfg.shot_id,
                    success=False,
                    warnings=[f"unexpected exception: {type(exc).__name__}: {exc}"],
                )
            report.total_attempts += 1

            if assembly.success:
                _append_jsonl(jsonl_path, _progress(
                    cfg.shot_id, attempt, max_attempts, "succeeded", assembly,
                    note=f"success on attempt {attempt}",
                ))
                final_assembly = assembly
                break

            # Failed
            if attempt < max_attempts:
                _append_jsonl(jsonl_path, _progress(
                    cfg.shot_id, attempt, max_attempts, "retrying", assembly,
                    note=f"will retry ({attempt}/{max_attempts})",
                ))
            else:
                _append_jsonl(jsonl_path, _progress(
                    cfg.shot_id, attempt, max_attempts, "exhausted", assembly,
                    note=f"retry budget exhausted after {attempt} attempt(s)",
                ))
                final_assembly = assembly

        if final_assembly is None:  # pragma: no cover - defensive
            final_assembly = ShotAssembly(
                shot_id=cfg.shot_id,
                success=False,
                warnings=["run_batch internal: no assembly produced"],
            )
        report.shots.append(final_assembly)

    report.finished_at = _now_iso()
    return report


def run_batch_sync(
    shots: list[ShotConfig],
    *,
    retry_count: int = 2,
    jsonl_path: Optional[Path] = None,
    rig_spec: Optional[RigSpec] = None,
) -> BatchReport:
    """Synchronous wrapper around `run_batch` for the CLI driver."""
    return asyncio.run(run_batch(
        shots,
        retry_count=retry_count,
        jsonl_path=jsonl_path,
        rig_spec=rig_spec,
    ))


# ─── AssemblyReport compatibility ─────────────────────────────────


def to_assembly_report(report: BatchReport) -> AssemblyReport:
    """Convert a BatchReport to the simpler AssemblyReport shape.

    Useful when downstream tooling still expects the original Phase 3l
    `animate_assembly.json` layout. BatchReport's extra fields
    (retry_count, jsonl_path, total_attempts) are dropped.
    """
    return AssemblyReport(shots=list(report.shots))
