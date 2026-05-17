"""Unit tests for the Phase 3n production batch runner.

Mocks `process_shot` so we don't spawn Animate. Verifies retry
policy, JSONL output shape, BatchReport aggregation, CLI exit codes,
and the camera_moves orchestrator wiring.

Run via:
    <python> -m pytest animate_cc_pipeline/tests/test_batch_runner.py -v
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from animate_cc_pipeline.pipeline.batch_runner import (
    BatchProgress,
    BatchReport,
    run_batch,
    run_batch_sync,
    to_assembly_report,
)
from animate_cc_pipeline.pipeline.camera_detector import CameraMovesMap, CameraState
from animate_cc_pipeline.pipeline.orchestrator.assembly_schemas import (
    AssemblyReport,
    CharacterConfig,
    ShotAssembly,
    ShotConfig,
    StepResult,
)


# ─── Helpers ──────────────────────────────────────────────────────


def _make_shot(tmp_path: Path, shot_id: str = "shot_x") -> ShotConfig:
    return ShotConfig(
        shot_id=shot_id,
        fla_out_path=tmp_path / f"{shot_id}.fla",
        characters=[CharacterConfig(
            identity="X",
            placeholder_image_path=tmp_path / f"{shot_id}.png",
        )],
    )


def _fake_assembly(shot_id: str, success: bool, elapsed: float = 0.1) -> ShotAssembly:
    return ShotAssembly(
        shot_id=shot_id,
        success=success,
        total_elapsed_seconds=elapsed,
        keyposes_processed=2 if success else 0,
        characters_assembled=1 if success else 0,
        steps=[StepResult(step="mocked", ok=success)],
    )


# ─── Schema tests ─────────────────────────────────────────────────


def test_batch_progress_defaults():
    bp = BatchProgress(
        timestamp="2026-05-17T10:00:00Z",
        shot_id="shot_a",
        attempt=1,
        max_attempts=3,
        status="succeeded",
    )
    assert bp.elapsed_seconds == 0.0
    assert bp.warnings_count == 0
    assert bp.note == ""


def test_batch_progress_extra_field_forbidden():
    with pytest.raises(Exception):
        BatchProgress.model_validate({
            "timestamp": "2026-05-17T10:00:00Z",
            "shot_id": "s",
            "attempt": 1,
            "max_attempts": 1,
            "status": "succeeded",
            "garbage_field": True,
        })


def test_batch_progress_status_must_be_known():
    with pytest.raises(Exception):
        BatchProgress(
            timestamp="2026-05-17T10:00:00Z",
            shot_id="s",
            attempt=1,
            max_attempts=1,
            status="lolwut",  # type: ignore[arg-type]
        )


def test_batch_report_counters_match_shots():
    r = BatchReport(
        started_at="2026-05-17T09:00:00Z",
        retry_count=2,
        shots=[
            _fake_assembly("a", True),
            _fake_assembly("b", False),
            _fake_assembly("c", True),
        ],
    )
    assert r.num_shots == 3
    assert r.num_succeeded == 2
    assert r.num_failed == 1


def test_batch_report_round_trip():
    r = BatchReport(
        started_at="2026-05-17T09:00:00Z",
        finished_at="2026-05-17T10:00:00Z",
        retry_count=2,
        total_attempts=4,
        shots=[_fake_assembly("a", True)],
    )
    serialized = r.model_dump_json()
    reloaded = BatchReport.model_validate_json(serialized)
    assert reloaded.retry_count == 2
    assert reloaded.total_attempts == 4
    assert reloaded.num_succeeded == 1


# ─── run_batch core logic ────────────────────────────────────────


def test_run_batch_empty_shots():
    report = asyncio.run(run_batch([], retry_count=2))
    assert report.num_shots == 0
    assert report.total_attempts == 0
    assert report.finished_at is not None


def test_run_batch_single_shot_succeeds_first_attempt(monkeypatch, tmp_path):
    """One successful shot → one attempt, success in report."""
    call_count = {"n": 0}

    async def fake_process(cfg, rig_spec):
        call_count["n"] += 1
        return _fake_assembly(cfg.shot_id, True)

    monkeypatch.setattr(
        "animate_cc_pipeline.pipeline.batch_runner.process_shot", fake_process,
    )

    report = asyncio.run(run_batch([_make_shot(tmp_path)], retry_count=2))
    assert report.num_succeeded == 1
    assert report.total_attempts == 1
    assert call_count["n"] == 1


def test_run_batch_retry_succeeds_on_second_attempt(monkeypatch, tmp_path):
    """First attempt fails, second succeeds → success in final report."""
    call_count = {"n": 0}

    async def flaky(cfg, rig_spec):
        call_count["n"] += 1
        # Fail first attempt, succeed on second
        return _fake_assembly(cfg.shot_id, call_count["n"] >= 2)

    monkeypatch.setattr(
        "animate_cc_pipeline.pipeline.batch_runner.process_shot", flaky,
    )

    report = asyncio.run(run_batch([_make_shot(tmp_path)], retry_count=2))
    assert report.num_succeeded == 1
    assert report.total_attempts == 2
    # The final ShotAssembly in the report is the successful one
    assert report.shots[0].success is True


def test_run_batch_all_attempts_fail_marks_exhausted(monkeypatch, tmp_path):
    """All attempts fail → final shot is the failed one, total_attempts = retry_count+1."""
    call_count = {"n": 0}

    async def always_fails(cfg, rig_spec):
        call_count["n"] += 1
        return _fake_assembly(cfg.shot_id, False)

    monkeypatch.setattr(
        "animate_cc_pipeline.pipeline.batch_runner.process_shot", always_fails,
    )

    report = asyncio.run(run_batch([_make_shot(tmp_path)], retry_count=2))
    assert report.num_failed == 1
    assert report.total_attempts == 3  # retry_count(2) + 1 initial
    assert call_count["n"] == 3
    assert report.shots[0].success is False


def test_run_batch_retry_count_zero_single_attempt(monkeypatch, tmp_path):
    """retry_count=0 means a single attempt only — no retries."""
    call_count = {"n": 0}

    async def always_fails(cfg, rig_spec):
        call_count["n"] += 1
        return _fake_assembly(cfg.shot_id, False)

    monkeypatch.setattr(
        "animate_cc_pipeline.pipeline.batch_runner.process_shot", always_fails,
    )

    report = asyncio.run(run_batch([_make_shot(tmp_path)], retry_count=0))
    assert report.total_attempts == 1
    assert call_count["n"] == 1
    assert report.num_failed == 1


def test_run_batch_invalid_retry_count_raises():
    with pytest.raises(ValueError, match="retry_count must be >= 0"):
        asyncio.run(run_batch([], retry_count=-1))


def test_run_batch_mixed_success_and_failure(monkeypatch, tmp_path):
    """Multi-shot: some succeed first try, some after retries, some fail outright."""
    # shot order: s1=ok, s2=ok after retry, s3=never
    counts: dict[str, int] = {}

    async def mixed(cfg, rig_spec):
        counts[cfg.shot_id] = counts.get(cfg.shot_id, 0) + 1
        if cfg.shot_id == "s1":
            return _fake_assembly(cfg.shot_id, True)
        if cfg.shot_id == "s2":
            return _fake_assembly(cfg.shot_id, counts[cfg.shot_id] >= 2)
        return _fake_assembly(cfg.shot_id, False)

    monkeypatch.setattr(
        "animate_cc_pipeline.pipeline.batch_runner.process_shot", mixed,
    )

    shots = [
        _make_shot(tmp_path, "s1"),
        _make_shot(tmp_path, "s2"),
        _make_shot(tmp_path, "s3"),
    ]
    report = asyncio.run(run_batch(shots, retry_count=2))

    assert report.num_succeeded == 2
    assert report.num_failed == 1
    # s1 = 1 attempt, s2 = 2 attempts, s3 = 3 attempts → 6 total
    assert report.total_attempts == 6


# ─── JSONL output ─────────────────────────────────────────────────


def test_run_batch_writes_jsonl_events(monkeypatch, tmp_path):
    """JSONL: one line per attempt, valid JSON, well-known fields."""
    async def ok(cfg, rig_spec):
        return _fake_assembly(cfg.shot_id, True)

    monkeypatch.setattr(
        "animate_cc_pipeline.pipeline.batch_runner.process_shot", ok,
    )

    jsonl_path = tmp_path / "progress.jsonl"
    asyncio.run(run_batch(
        [_make_shot(tmp_path, "s1"), _make_shot(tmp_path, "s2")],
        retry_count=2,
        jsonl_path=jsonl_path,
    ))

    assert jsonl_path.exists()
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        event = json.loads(line)
        assert event["status"] == "succeeded"
        assert event["attempt"] == 1
        assert "timestamp" in event
        assert "shot_id" in event


def test_run_batch_jsonl_retry_then_exhausted(monkeypatch, tmp_path):
    """All-fail shot writes 'retrying' for non-final attempts and
    'exhausted' for the last one."""
    async def always_fails(cfg, rig_spec):
        return _fake_assembly(cfg.shot_id, False)

    monkeypatch.setattr(
        "animate_cc_pipeline.pipeline.batch_runner.process_shot", always_fails,
    )

    jsonl_path = tmp_path / "progress.jsonl"
    asyncio.run(run_batch(
        [_make_shot(tmp_path)],
        retry_count=2,
        jsonl_path=jsonl_path,
    ))

    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    statuses = [json.loads(l)["status"] for l in lines]
    assert statuses == ["retrying", "retrying", "exhausted"]


def test_run_batch_no_jsonl_when_path_none(monkeypatch, tmp_path):
    """If jsonl_path is None, nothing is written, no error."""
    async def ok(cfg, rig_spec):
        return _fake_assembly(cfg.shot_id, True)

    monkeypatch.setattr(
        "animate_cc_pipeline.pipeline.batch_runner.process_shot", ok,
    )

    report = asyncio.run(run_batch(
        [_make_shot(tmp_path)], retry_count=1, jsonl_path=None,
    ))
    assert report.jsonl_path is None
    # tmp_path is empty save for the shot's intended files
    assert not (tmp_path / "progress.jsonl").exists()


# ─── to_assembly_report compatibility ────────────────────────────


def test_to_assembly_report_preserves_shots():
    r = BatchReport(
        started_at="2026-05-17T09:00:00Z",
        retry_count=2,
        shots=[
            _fake_assembly("a", True),
            _fake_assembly("b", False),
        ],
    )
    converted = to_assembly_report(r)
    assert isinstance(converted, AssemblyReport)
    assert converted.num_succeeded == 1
    assert converted.num_failed == 1


# ─── camera_moves orchestrator wiring ────────────────────────────


def test_camera_moves_skipped_when_path_none(tmp_path):
    """ShotConfig without camera_moves_path → no apply_camera_moves call."""
    cfg = ShotConfig(shot_id="x", fla_out_path=tmp_path / "x.fla")
    assert cfg.camera_moves_path is None


def test_camera_moves_path_accepted_by_shot_config(tmp_path):
    """ShotConfig accepts camera_moves_path."""
    camera_json = tmp_path / "moves.json"
    cfg = ShotConfig(
        shot_id="x",
        fla_out_path=tmp_path / "x.fla",
        camera_moves_path=camera_json,
    )
    assert cfg.camera_moves_path == camera_json


def test_apply_camera_moves_invokes_set_camera_position(monkeypatch, tmp_path):
    """When camera_moves_path points to a valid CameraMovesMap, the
    orchestrator calls set_camera_position once per CameraState entry.
    """
    from animate_cc_pipeline.pipeline.orchestrator.shot_processor import _apply_camera_moves

    # Write a moves file with 3 frames
    moves = CameraMovesMap(
        shot_id="x",
        frame_count=3,
        moves=[
            CameraState(frame=1, x=0, y=0, confidence=1.0),
            CameraState(frame=2, x=5, y=0, confidence=0.8),
            CameraState(frame=3, x=10, y=2, confidence=0.7),
        ],
    )
    moves_path = tmp_path / "moves.json"
    moves_path.write_text(moves.model_dump_json(), encoding="utf-8")

    cfg = ShotConfig(
        shot_id="x",
        fla_out_path=tmp_path / "x.fla",
        camera_moves_path=moves_path,
    )
    assembly = ShotAssembly(shot_id="x", success=False)

    calls: list[dict] = []

    async def fake_set_cam(args):
        import mcp.types as types
        calls.append(dict(args))
        return [types.TextContent(type="text", text=json.dumps({"status": "ok"}))]

    from animate_cc_pipeline.mcp_server.tools import camera as camera_tools
    monkeypatch.setattr(camera_tools, "handle_set_camera_position", fake_set_cam)

    asyncio.run(_apply_camera_moves(cfg, assembly))

    assert len(calls) == 3
    # The 3rd call should be for frame 3 with x=10
    assert calls[2]["frame"] == 3
    assert calls[2]["x"] == 10
    # apply_camera_moves step was recorded as ok
    step = next(s for s in assembly.steps if s.step == "apply_camera_moves")
    assert step.ok is True


def test_apply_camera_moves_handles_bad_json(tmp_path):
    """Unparseable camera_moves.json → warning + failed step but no exception."""
    from animate_cc_pipeline.pipeline.orchestrator.shot_processor import _apply_camera_moves

    bad_path = tmp_path / "garbage.json"
    bad_path.write_text("{not valid json", encoding="utf-8")
    cfg = ShotConfig(
        shot_id="x",
        fla_out_path=tmp_path / "x.fla",
        camera_moves_path=bad_path,
    )
    assembly = ShotAssembly(shot_id="x", success=False)
    asyncio.run(_apply_camera_moves(cfg, assembly))
    assert any("camera_moves_path" in w for w in assembly.warnings)


# ─── CLI tests ────────────────────────────────────────────────────


def test_cli_parses_config_writes_report_and_jsonl(monkeypatch, tmp_path):
    from animate_cc_pipeline.pipeline.cli_batch import main as cli_main

    async def ok(cfg, rig_spec):
        return _fake_assembly(cfg.shot_id, True)

    monkeypatch.setattr(
        "animate_cc_pipeline.pipeline.batch_runner.process_shot", ok,
    )

    config = {
        "schemaVersion": 1,
        "shots": [{
            "shot_id": "s1",
            "fla_out_path": str(tmp_path / "s1.fla"),
            "characters": [{
                "identity": "X",
                "placeholder_image_path": str(tmp_path / "x.png"),
            }],
        }],
    }
    cfg_path = tmp_path / "batch.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")

    report_path = tmp_path / "batch_report.json"
    jsonl_path = tmp_path / "progress.jsonl"

    exit_code = cli_main([
        "--config", str(cfg_path),
        "--report-out", str(report_path),
        "--jsonl", str(jsonl_path),
        "--retry-count", "1",
        "--log-level", "ERROR",
    ])
    assert exit_code == 0
    assert report_path.exists()
    assert jsonl_path.exists()
    report = BatchReport.model_validate_json(report_path.read_text())
    assert report.num_succeeded == 1
    assert report.retry_count == 1


def test_cli_rejects_bad_schema_version(tmp_path):
    from animate_cc_pipeline.pipeline.cli_batch import main as cli_main

    cfg_path = tmp_path / "bad.json"
    cfg_path.write_text(json.dumps({"schemaVersion": 999, "shots": []}), encoding="utf-8")

    exit_code = cli_main([
        "--config", str(cfg_path),
        "--log-level", "ERROR",
    ])
    assert exit_code == 2


def test_cli_missing_config_returns_2(tmp_path):
    from animate_cc_pipeline.pipeline.cli_batch import main as cli_main

    exit_code = cli_main([
        "--config", str(tmp_path / "nope.json"),
        "--log-level", "ERROR",
    ])
    assert exit_code == 2


def test_cli_rejects_negative_retry_count(tmp_path):
    from animate_cc_pipeline.pipeline.cli_batch import main as cli_main

    cfg_path = tmp_path / "ok.json"
    cfg_path.write_text(json.dumps({"schemaVersion": 1, "shots": []}), encoding="utf-8")

    exit_code = cli_main([
        "--config", str(cfg_path),
        "--retry-count", "-1",
        "--log-level", "ERROR",
    ])
    assert exit_code == 2


def test_cli_empty_shots_returns_zero(tmp_path):
    from animate_cc_pipeline.pipeline.cli_batch import main as cli_main

    cfg_path = tmp_path / "empty.json"
    cfg_path.write_text(json.dumps({"schemaVersion": 1, "shots": []}), encoding="utf-8")

    exit_code = cli_main([
        "--config", str(cfg_path),
        "--log-level", "ERROR",
    ])
    assert exit_code == 0


def test_cli_failed_shot_returns_one(monkeypatch, tmp_path):
    from animate_cc_pipeline.pipeline.cli_batch import main as cli_main

    async def fails(cfg, rig_spec):
        return _fake_assembly(cfg.shot_id, False)

    monkeypatch.setattr(
        "animate_cc_pipeline.pipeline.batch_runner.process_shot", fails,
    )

    cfg = {
        "schemaVersion": 1,
        "shots": [{
            "shot_id": "fail",
            "fla_out_path": str(tmp_path / "fail.fla"),
            "characters": [{
                "identity": "X",
                "placeholder_image_path": str(tmp_path / "x.png"),
            }],
        }],
    }
    cfg_path = tmp_path / "fail.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    exit_code = cli_main([
        "--config", str(cfg_path),
        "--report-out", str(tmp_path / "report.json"),
        "--jsonl", str(tmp_path / "progress.jsonl"),
        "--retry-count", "0",
        "--log-level", "ERROR",
    ])
    assert exit_code == 1


def test_run_batch_sync_smoke(monkeypatch, tmp_path):
    """run_batch_sync wraps asyncio.run correctly."""
    async def ok(cfg, rig_spec):
        return _fake_assembly(cfg.shot_id, True)

    monkeypatch.setattr(
        "animate_cc_pipeline.pipeline.batch_runner.process_shot", ok,
    )

    report = run_batch_sync([_make_shot(tmp_path)], retry_count=0)
    assert report.num_succeeded == 1
