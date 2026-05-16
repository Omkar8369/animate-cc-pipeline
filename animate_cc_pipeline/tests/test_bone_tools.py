"""Unit tests for Phase 3f bone/graphic tools.

No Animate.exe spawn. Verifies tool registration, JSFL template
presence, schema validation, argument-validation paths.

Run via:
    <python> -m pytest animate_cc_pipeline/tests/test_bone_tools.py -v
"""

from __future__ import annotations

import asyncio
import json

import pytest


def _all_tool_names():
    from animate_cc_pipeline.mcp_server.server import handle_list_tools

    tools = asyncio.run(handle_list_tools())
    return {t.name for t in tools}


def test_server_lists_all_phase3f_tools():
    expected = {"set_graphic_first_frame", "get_graphic_first_frame", "validate_rig"}
    assert _all_tool_names() >= expected


def test_server_version_at_least_0_5():
    from animate_cc_pipeline.mcp_server.server import SERVER_VERSION

    major, minor = (int(p) for p in SERVER_VERSION.split(".")[:2])
    assert (major, minor) >= (0, 5), f"expected >=0.5.x for Phase 3f, got {SERVER_VERSION}"


def test_phase3f_jsfl_templates_exist():
    from animate_cc_pipeline.mcp_server.tools.bone import JSFL_TEMPLATES_DIR

    for name in [
        "set_graphic_first_frame.jsfl",
        "get_graphic_first_frame.jsfl",
        "dump_rig_structure.jsfl",
    ]:
        p = JSFL_TEMPLATES_DIR / name
        assert p.exists(), f"missing JSFL template: {p}"
        assert p.stat().st_size > 0


def test_set_graphic_first_frame_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.bone import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "set_graphic_first_frame.jsfl").read_text(encoding="utf-8")
    for placeholder in [
        "{{FLA_PATH}}", "{{LAYER_NAME}}", "{{FRAME}}",
        "{{TARGET_FIRST_FRAME}}", "{{LOOP_MODE}}", "{{SENTINEL_PATH}}",
    ]:
        assert placeholder in content, f"missing {placeholder}"


def test_get_graphic_first_frame_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.bone import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "get_graphic_first_frame.jsfl").read_text(encoding="utf-8")
    for placeholder in [
        "{{FLA_PATH}}", "{{LAYER_NAME}}", "{{FRAME}}",
        "{{OUT_JSON_PATH}}", "{{SENTINEL_PATH}}",
    ]:
        assert placeholder in content, f"missing {placeholder}"


def test_dump_rig_structure_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.bone import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "dump_rig_structure.jsfl").read_text(encoding="utf-8")
    for placeholder in ["{{FLA_PATH}}", "{{OUT_JSON_PATH}}", "{{SENTINEL_PATH}}"]:
        assert placeholder in content, f"missing {placeholder}"


def test_dispatcher_has_all_phase3f_handlers():
    from animate_cc_pipeline.mcp_server.server import TOOL_HANDLERS

    for name in ["set_graphic_first_frame", "get_graphic_first_frame", "validate_rig"]:
        assert name in TOOL_HANDLERS


def test_set_graphic_first_frame_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import bone

    result = asyncio.run(bone.handle_set_graphic_first_frame({
        "fla_path": str(tmp_path / "missing.fla"),
        "layer_name": "ARM",
        "target_first_frame": 2,
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_set_graphic_first_frame_rejects_bad_loop_mode(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import bone

    fla = tmp_path / "test.fla"
    fla.write_bytes(b"\x00")
    result = asyncio.run(bone.handle_set_graphic_first_frame({
        "fla_path": str(fla),
        "layer_name": "ARM",
        "target_first_frame": 2,
        "loop_mode": "infinity",  # invalid
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "loop_mode must be one of" in payload["error"]


def test_get_graphic_first_frame_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import bone

    result = asyncio.run(bone.handle_get_graphic_first_frame({
        "fla_path": str(tmp_path / "missing.fla"),
        "layer_name": "ARM",
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"


def test_validate_rig_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import bone

    result = asyncio.run(bone.handle_validate_rig({
        "fla_path": str(tmp_path / "missing.fla"),
        "identity": "JETHALAL",
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_phase3f_tool_descriptions_non_empty():
    from animate_cc_pipeline.mcp_server.tools.bone import ALL_TOOLS

    for tool in ALL_TOOLS:
        assert tool.description
        assert len(tool.description) >= 30


def test_phase3f_tool_schemas_strict():
    from animate_cc_pipeline.mcp_server.tools.bone import ALL_TOOLS

    for tool in ALL_TOOLS:
        assert tool.inputSchema.get("additionalProperties") is False


def test_total_tool_count_phase3f():
    """1 ping + 5 doc + 4 symbol + 4 keyframe + 3 bone = 17."""
    names = _all_tool_names()
    assert len(names) >= 17, f"expected >=17 tools, got {sorted(names)}"


def test_valid_loop_modes_constant():
    from animate_cc_pipeline.mcp_server.tools.bone import VALID_LOOP_MODES

    # Match Animate's actual instance.loop enum
    assert "loop" in VALID_LOOP_MODES
    assert "play once" in VALID_LOOP_MODES
    assert "single frame" in VALID_LOOP_MODES
