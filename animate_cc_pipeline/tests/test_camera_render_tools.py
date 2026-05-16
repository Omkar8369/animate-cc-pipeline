"""Unit tests for Phase 3i camera + render tools.

No Animate.exe spawn. Verifies registration, JSFL templates,
schemas, argument validation.

Run via:
    <python> -m pytest animate_cc_pipeline/tests/test_camera_render_tools.py -v
"""

from __future__ import annotations

import asyncio
import json


def _all_tool_names():
    from animate_cc_pipeline.mcp_server.server import handle_list_tools

    tools = asyncio.run(handle_list_tools())
    return {t.name for t in tools}


def test_server_lists_all_phase3i_tools():
    expected = {"set_camera_position", "render_to_mp4", "render_preview"}
    assert _all_tool_names() >= expected


def test_server_version_at_least_0_8():
    from animate_cc_pipeline.mcp_server.server import SERVER_VERSION

    major, minor = (int(p) for p in SERVER_VERSION.split(".")[:2])
    assert (major, minor) >= (0, 8), f"expected >=0.8.x for Phase 3i, got {SERVER_VERSION}"


def test_phase3i_jsfl_templates_exist():
    from animate_cc_pipeline.mcp_server.tools.camera import JSFL_TEMPLATES_DIR

    for name in ["set_camera_position.jsfl", "export_png_sequence.jsfl"]:
        p = JSFL_TEMPLATES_DIR / name
        assert p.exists(), f"missing JSFL template: {p}"
        assert p.stat().st_size > 0


def test_set_camera_position_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.camera import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "set_camera_position.jsfl").read_text(encoding="utf-8")
    for placeholder in [
        "{{FLA_PATH}}", "{{FRAME}}", "{{X}}", "{{Y}}",
        "{{ZOOM}}", "{{ROTATION}}", "{{SENTINEL_PATH}}",
    ]:
        assert placeholder in content


def test_export_png_sequence_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.camera import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "export_png_sequence.jsfl").read_text(encoding="utf-8")
    for placeholder in [
        "{{FLA_PATH}}", "{{PNG_PREFIX_PATH}}",
        "{{START_FRAME_IDX0}}", "{{END_FRAME_IDX0}}", "{{SENTINEL_PATH}}",
    ]:
        assert placeholder in content


def test_dispatcher_has_all_phase3i_handlers():
    from animate_cc_pipeline.mcp_server.server import TOOL_HANDLERS

    for name in ["set_camera_position", "render_to_mp4", "render_preview"]:
        assert name in TOOL_HANDLERS


def test_set_camera_position_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import camera

    result = asyncio.run(camera.handle_set_camera_position({
        "fla_path": str(tmp_path / "missing.fla"),
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_render_to_mp4_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import camera

    result = asyncio.run(camera.handle_render_to_mp4({
        "fla_path": str(tmp_path / "missing.fla"),
        "out_path": str(tmp_path / "out.mp4"),
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_render_preview_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import camera

    result = asyncio.run(camera.handle_render_preview({
        "fla_path": str(tmp_path / "missing.fla"),
        "out_path": str(tmp_path / "out.mp4"),
        "start_frame": 1,
        "end_frame": 5,
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"


def test_render_preview_rejects_invalid_range(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import camera

    fla = tmp_path / "exists.fla"
    fla.write_bytes(b"\x00")
    result = asyncio.run(camera.handle_render_preview({
        "fla_path": str(fla),
        "out_path": str(tmp_path / "out.mp4"),
        "start_frame": 10,
        "end_frame": 5,  # invalid
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "must be" in payload["error"]


def test_phase3i_tool_descriptions_non_empty():
    from animate_cc_pipeline.mcp_server.tools.camera import ALL_TOOLS

    for tool in ALL_TOOLS:
        assert tool.description
        assert len(tool.description) >= 30


def test_phase3i_tool_schemas_strict():
    from animate_cc_pipeline.mcp_server.tools.camera import ALL_TOOLS

    for tool in ALL_TOOLS:
        assert tool.inputSchema.get("additionalProperties") is False


def test_total_tool_count_phase3i():
    """1 ping + 5 doc + 4 symbol + 4 keyframe + 3 bone + 3 tween + 3 audio + 3 camera = 26."""
    names = _all_tool_names()
    assert len(names) >= 26, f"expected >=26 tools, got {sorted(names)}"


def test_set_camera_position_marked_experimental():
    """The tool description must communicate experimental status."""
    from animate_cc_pipeline.mcp_server.tools.camera import SET_CAMERA_POSITION_TOOL

    assert "experimental" in SET_CAMERA_POSITION_TOOL.description.lower()


def test_render_tools_default_fps():
    """Both render tools default fps to 25 (Indian animation standard, 25 FPS PAL)."""
    from animate_cc_pipeline.mcp_server.tools.camera import (
        RENDER_TO_MP4_TOOL, RENDER_PREVIEW_TOOL,
    )

    for tool in (RENDER_TO_MP4_TOOL, RENDER_PREVIEW_TOOL):
        fps_default = tool.inputSchema["properties"]["fps"].get("default")
        assert fps_default == 25, f"{tool.name} fps default should be 25, got {fps_default}"
