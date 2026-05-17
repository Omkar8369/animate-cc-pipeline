"""Unit tests for the orchestrator (shot_processor + CLI).

Mocks every MCP tool handler so tests don't spawn Animate. Verifies
step ordering, error propagation, and report shape.

Run via:
    <python> -m pytest animate_cc_pipeline/tests/test_orchestrator.py -v
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from animate_cc_pipeline.mcp_server import jsfl_bridge
from animate_cc_pipeline.pipeline.orchestrator.assembly_schemas import (
    AssemblyReport,
    CharacterConfig,
    ShotAssembly,
    ShotConfig,
)


# ─── Mock-everything fixture ───────────────────────────────────────


@pytest.fixture
def mock_handlers(monkeypatch):
    """Patch every MCP tool handler to return a fake "ok" response.

    Records each call so tests can assert on the order + arguments.
    """
    from animate_cc_pipeline.mcp_server.tools import (
        audio as audio_tools, bone as bone_tools, camera as camera_tools,
        document as document_tools, keyframe as keyframe_tools,
        symbol as symbol_tools, tween as tween_tools,
    )
    import mcp.types as types

    calls: list[tuple[str, dict]] = []

    def make_handler(tool_name: str, ok: bool = True, extra: dict | None = None):
        async def handler(args):
            calls.append((tool_name, dict(args or {})))
            payload = {
                "status": "ok" if ok else "error",
                "elapsed_seconds": 0.01,
                **(extra or {}),
            }
            if not ok:
                payload["error"] = "mocked failure"
            return [types.TextContent(type="text", text=json.dumps(payload))]
        return handler

    monkeypatch.setattr(document_tools, "handle_create_document", make_handler("create_document"))
    monkeypatch.setattr(document_tools, "handle_save_document", make_handler("save_document"))
    monkeypatch.setattr(document_tools, "handle_import_video_as_layer", make_handler("import_video_as_layer"))
    monkeypatch.setattr(document_tools, "handle_import_image_as_layer", make_handler("import_image_as_layer"))
    monkeypatch.setattr(document_tools, "handle_import_character_rig", make_handler(
        "import_character_rig", extra={"instance_placed": True},
    ))
    monkeypatch.setattr(symbol_tools, "handle_set_instance_position", make_handler("set_instance_position"))
    monkeypatch.setattr(symbol_tools, "handle_set_instance_scale", make_handler("set_instance_scale"))
    monkeypatch.setattr(symbol_tools, "handle_set_instance_rotation", make_handler("set_instance_rotation"))
    monkeypatch.setattr(keyframe_tools, "handle_insert_keyframe", make_handler("insert_keyframe"))
    monkeypatch.setattr(bone_tools, "handle_set_graphic_first_frame", make_handler("set_graphic_first_frame"))
    monkeypatch.setattr(tween_tools, "handle_add_classic_tween", make_handler("add_classic_tween"))
    monkeypatch.setattr(audio_tools, "handle_import_audio", make_handler("import_audio"))
    monkeypatch.setattr(camera_tools, "handle_render_to_mp4", make_handler("render_to_mp4",
        extra={"out_size_bytes": 1234, "frame_count": 10}))

    return calls


def test_minimal_shot_no_characters(mock_handlers, tmp_path):
    """create_document → save_document → (no characters, no render)"""
    from animate_cc_pipeline.pipeline.orchestrator.shot_processor import process_shot

    cfg = ShotConfig(
        shot_id="shot_001",
        fla_out_path=tmp_path / "out.fla",
    )
    assembly = asyncio.run(process_shot(cfg))
    # No characters → success=False (no character assembled)
    assert assembly.success is False
    assert assembly.shot_id == "shot_001"
    # But create + save should have been attempted
    tool_names = [c[0] for c in mock_handlers]
    assert "create_document" in tool_names
    assert "save_document" in tool_names


def test_shot_with_placeholder_character(mock_handlers, tmp_path):
    """A placeholder character runs through import_image, save, and
    render even without a pose map.
    """
    from animate_cc_pipeline.pipeline.orchestrator.shot_processor import process_shot

    char = CharacterConfig(
        identity="JETHALAL",
        placeholder_image_path=tmp_path / "fake.png",
    )
    cfg = ShotConfig(
        shot_id="shot_001",
        fla_out_path=tmp_path / "out.fla",
        mp4_out_path=tmp_path / "out.mp4",
        characters=[char],
    )
    assembly = asyncio.run(process_shot(cfg))
    assert assembly.success is True
    assert assembly.characters_assembled == 1
    assert assembly.mp4_out_path == cfg.mp4_out_path
    tool_names = [c[0] for c in mock_handlers]
    assert "create_document" in tool_names
    assert "import_image_as_layer" in tool_names
    assert "save_document" in tool_names
    assert "render_to_mp4" in tool_names


def test_step_order_for_placeholder_character(mock_handlers, tmp_path):
    """Verify step order matches the orchestrator's contract:
    create -> animatic -> background -> import character -> save -> render."""
    from animate_cc_pipeline.pipeline.orchestrator.shot_processor import process_shot

    char = CharacterConfig(
        identity="TAPPU",
        placeholder_image_path=tmp_path / "tappu.png",
    )
    cfg = ShotConfig(
        shot_id="shot_x",
        fla_out_path=tmp_path / "x.fla",
        mp4_out_path=tmp_path / "x.mp4",
        background_image_path=tmp_path / "bg.png",
        characters=[char],
    )
    asyncio.run(process_shot(cfg))
    tool_names = [c[0] for c in mock_handlers]
    # Assert the relative order of key milestones
    assert tool_names.index("create_document") < tool_names.index("import_image_as_layer")
    assert tool_names.index("save_document") < tool_names.index("render_to_mp4")


def test_skip_animatic_when_path_none(mock_handlers, tmp_path):
    from animate_cc_pipeline.pipeline.orchestrator.shot_processor import process_shot

    cfg = ShotConfig(
        shot_id="shot_z",
        fla_out_path=tmp_path / "z.fla",
        # no animatic_mp4_path
    )
    asyncio.run(process_shot(cfg))
    tool_names = [c[0] for c in mock_handlers]
    assert "import_video_as_layer" not in tool_names


def test_apply_keyframes_when_pose_map_present(mock_handlers, tmp_path):
    """If pose_map.json is present, the orchestrator emits a keyframe
    per pose-map frame."""
    from animate_cc_pipeline.pipeline.orchestrator.shot_processor import process_shot
    from animate_cc_pipeline.pipeline.schemas import (
        Bbox, CharacterPose, FramePoseSet, Joint, JointSet, PoseMap,
    )

    # Synthesize a pose_map with 3 frames
    j = lambda x, y: Joint(x=x, y=y, confidence=0.9)
    js = JointSet(
        nose=j(100, 50), neck=j(100, 100),
        shoulder_L=j(80, 110), shoulder_R=j(120, 110),
    )
    cp = CharacterPose(
        identity="TAPPU",
        bbox=Bbox(x=0, y=0, w=100, h=200),
        joints=js,
    )
    pose_map = PoseMap(
        shotId="shot_x",
        frames={
            "1": FramePoseSet(frameIndex=1, characters=[cp]),
            "10": FramePoseSet(frameIndex=10, characters=[cp]),
            "20": FramePoseSet(frameIndex=20, characters=[cp]),
        },
    )
    pose_map_path = tmp_path / "pose_map.json"
    pose_map_path.write_text(pose_map.model_dump_json(), encoding="utf-8")

    char = CharacterConfig(
        identity="TAPPU",
        placeholder_image_path=tmp_path / "fake.png",
        pose_map_path=pose_map_path,
    )
    cfg = ShotConfig(
        shot_id="shot_x",
        fla_out_path=tmp_path / "x.fla",
        characters=[char],
    )
    assembly = asyncio.run(process_shot(cfg))
    assert assembly.keyposes_processed == 3
    # 3 insert_keyframe calls — one per frame
    insert_kf_count = sum(1 for c in mock_handlers if c[0] == "insert_keyframe")
    assert insert_kf_count == 3
    # 2 add_classic_tween calls — between consecutive frames (1→10, 10→20)
    tween_count = sum(1 for c in mock_handlers if c[0] == "add_classic_tween")
    assert tween_count == 2


def test_failure_in_create_document_aborts_processing(monkeypatch, tmp_path):
    """If create_document fails, the orchestrator returns early with
    success=False and no downstream tools are called."""
    from animate_cc_pipeline.mcp_server.tools import document as document_tools
    from animate_cc_pipeline.pipeline.orchestrator.shot_processor import process_shot
    import mcp.types as types

    async def bad_create(args):
        return [types.TextContent(type="text", text=json.dumps({
            "status": "error", "error": "simulated create failure",
        }))]

    monkeypatch.setattr(document_tools, "handle_create_document", bad_create)

    cfg = ShotConfig(
        shot_id="shot_fail",
        fla_out_path=tmp_path / "fail.fla",
    )
    assembly = asyncio.run(process_shot(cfg))
    assert assembly.success is False
    # The failure should be recorded as a failed step
    failed = [s for s in assembly.steps if not s.ok]
    assert any(s.step == "create_document" for s in failed)


def test_rig_path_calls_import_character_rig(mock_handlers, tmp_path):
    """Phase 3o-code + 3o-adapter: a CharacterConfig with rig_fla_path
    triggers import_character_rig (instead of the warning-and-skip
    from earlier phases). The character is counted as assembled.
    The handler's `identity` arg is the angle (resolved against the
    rig's labels.json sidecar inside the handler) — the on-canvas
    layer name is the character's display name."""
    from animate_cc_pipeline.pipeline.orchestrator.shot_processor import process_shot

    char = CharacterConfig(
        identity="JETHALAL",
        rig_fla_path=tmp_path / "jethalal.fla",
        angle="side_l",
    )
    cfg = ShotConfig(
        shot_id="shot_w",
        fla_out_path=tmp_path / "w.fla",
        characters=[char],
    )
    assembly = asyncio.run(process_shot(cfg))
    tool_names = [c[0] for c in mock_handlers]
    assert "import_character_rig" in tool_names
    rig_call = next(c for c in mock_handlers if c[0] == "import_character_rig")
    # identity arg = the angle to resolve via sidecar
    assert rig_call[1]["identity"] == "side_l"
    # layer_name = the character's display name
    assert rig_call[1]["layer_name"] == "JETHALAL"
    assert rig_call[1]["rig_fla_path"].endswith("jethalal.fla")
    # Character is now ASSEMBLED (Phase 3o-code unblocks this)
    assert assembly.characters_assembled == 1


def test_rig_path_default_angle_is_front(mock_handlers, tmp_path):
    """When CharacterConfig.angle isn't set, the default 'front'
    is passed as the identity to the rig handler."""
    from animate_cc_pipeline.pipeline.orchestrator.shot_processor import process_shot

    char = CharacterConfig(
        identity="JETHALAL",
        rig_fla_path=tmp_path / "jethalal.fla",
        # angle omitted -> default "front"
    )
    cfg = ShotConfig(
        shot_id="shot_w",
        fla_out_path=tmp_path / "w.fla",
        characters=[char],
    )
    asyncio.run(process_shot(cfg))
    rig_call = next(c for c in mock_handlers if c[0] == "import_character_rig")
    assert rig_call[1]["identity"] == "front"


def test_rig_path_warns_when_instance_not_placed(monkeypatch, tmp_path):
    """If the rig library imports but the instance can't be placed
    (e.g. symbol name mismatch), the orchestrator warns and skips
    the character rather than continuing with a phantom layer."""
    from animate_cc_pipeline.mcp_server.tools import document as document_tools
    from animate_cc_pipeline.pipeline.orchestrator.shot_processor import process_shot
    import mcp.types as types

    async def rig_handler(args):
        payload = {
            "status": "ok",
            "elapsed_seconds": 0.01,
            "instance_placed": False,
            "warning": "symbol not found",
        }
        return [types.TextContent(type="text", text=json.dumps(payload))]

    async def noop_ok(args):
        return [types.TextContent(type="text", text=json.dumps({"status": "ok"}))]

    monkeypatch.setattr(document_tools, "handle_create_document", noop_ok)
    monkeypatch.setattr(document_tools, "handle_save_document", noop_ok)
    monkeypatch.setattr(document_tools, "handle_import_character_rig", rig_handler)

    char = CharacterConfig(identity="MYSTERY", rig_fla_path=tmp_path / "ghost.fla")
    cfg = ShotConfig(
        shot_id="shot_g",
        fla_out_path=tmp_path / "g.fla",
        characters=[char],
    )
    assembly = asyncio.run(process_shot(cfg))
    # The character is NOT counted as assembled
    assert assembly.characters_assembled == 0
    # A warning was recorded
    assert any("instance not placed" in w.lower() for w in assembly.warnings)


def test_assembly_report_aggregates_correctly(mock_handlers, tmp_path):
    from animate_cc_pipeline.pipeline.orchestrator.shot_processor import process_shots
    char1 = CharacterConfig(identity="A", placeholder_image_path=tmp_path / "a.png")
    char2 = CharacterConfig(identity="B", placeholder_image_path=tmp_path / "b.png")
    shots = [
        ShotConfig(shot_id="s1", fla_out_path=tmp_path / "s1.fla", characters=[char1]),
        ShotConfig(shot_id="s2", fla_out_path=tmp_path / "s2.fla", characters=[char2]),
    ]
    report = asyncio.run(process_shots(shots))
    assert len(report.shots) == 2
    assert report.num_succeeded == 2
    assert report.num_failed == 0


# ─── CLI tests ─────────────────────────────────────────────────────


def test_cli_parses_config_and_writes_report(monkeypatch, mock_handlers, tmp_path):
    from animate_cc_pipeline.pipeline.orchestrator.cli_node7_animate import main as cli_main

    config = {
        "schemaVersion": 1,
        "shots": [{
            "shot_id": "shot_001",
            "fla_out_path": str(tmp_path / "out.fla"),
            "characters": [{
                "identity": "TAPPU",
                "placeholder_image_path": str(tmp_path / "tappu.png"),
            }],
        }],
    }
    cfg_path = tmp_path / "batch.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")

    exit_code = cli_main([
        "--config", str(cfg_path),
        "--report-out", str(tmp_path / "report.json"),
        "--log-level", "ERROR",
    ])
    assert exit_code == 0
    assert (tmp_path / "report.json").exists()
    report = AssemblyReport.model_validate_json((tmp_path / "report.json").read_text())
    assert report.num_succeeded == 1


def test_cli_rejects_bad_schema_version(tmp_path):
    from animate_cc_pipeline.pipeline.orchestrator.cli_node7_animate import main as cli_main

    cfg_path = tmp_path / "bad.json"
    cfg_path.write_text(json.dumps({"schemaVersion": 999, "shots": []}), encoding="utf-8")

    exit_code = cli_main([
        "--config", str(cfg_path),
        "--log-level", "ERROR",
    ])
    assert exit_code == 2


def test_cli_empty_shots_returns_zero(monkeypatch, tmp_path):
    from animate_cc_pipeline.pipeline.orchestrator.cli_node7_animate import main as cli_main

    cfg_path = tmp_path / "empty.json"
    cfg_path.write_text(json.dumps({"schemaVersion": 1, "shots": []}), encoding="utf-8")

    exit_code = cli_main([
        "--config", str(cfg_path),
        "--log-level", "ERROR",
    ])
    assert exit_code == 0


# ─── Schema tests ──────────────────────────────────────────────────


def test_character_config_extra_field_forbidden():
    with pytest.raises(Exception):
        CharacterConfig(identity="X", placeholder_image_path=Path("p.png"), extra="nope")


def test_shot_assembly_default_failure():
    sa = ShotAssembly(shot_id="x", success=False)
    assert sa.warnings == []
    assert sa.steps == []
    assert sa.keyposes_processed == 0


def test_assembly_report_round_trip():
    r = AssemblyReport(
        schemaVersion=1,
        shots=[ShotAssembly(shot_id="x", success=True, total_elapsed_seconds=1.5)],
    )
    serialized = r.model_dump_json()
    reloaded = AssemblyReport.model_validate_json(serialized)
    assert reloaded.num_succeeded == 1
