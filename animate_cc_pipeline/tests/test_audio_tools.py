"""Unit tests for Phase 3h audio + lipsync tools.

No Animate.exe spawn. Verifies tool registration, JSFL template
presence, argument validation, dispatcher routing.

Run via:
    <python> -m pytest animate_cc_pipeline/tests/test_audio_tools.py -v
"""

from __future__ import annotations

import asyncio
import json

import pytest


def _all_tool_names():
    from animate_cc_pipeline.mcp_server.server import handle_list_tools

    tools = asyncio.run(handle_list_tools())
    return {t.name for t in tools}


def test_server_lists_all_phase3h_tools():
    expected = {"import_audio", "set_switch_state", "apply_auto_lipsync"}
    assert _all_tool_names() >= expected


def test_server_version_at_least_0_7():
    from animate_cc_pipeline.mcp_server.server import SERVER_VERSION

    major, minor = (int(p) for p in SERVER_VERSION.split(".")[:2])
    assert (major, minor) >= (0, 7), f"expected >=0.7.x for Phase 3h, got {SERVER_VERSION}"


def test_phase3h_jsfl_templates_exist():
    from animate_cc_pipeline.mcp_server.tools.audio import JSFL_TEMPLATES_DIR

    for name in [
        "import_audio.jsfl",
        "set_switch_state.jsfl",
        "apply_auto_lipsync.jsfl",
        "_setup_phase3h_test_fla.jsfl",
    ]:
        p = JSFL_TEMPLATES_DIR / name
        assert p.exists(), f"missing JSFL template: {p}"
        assert p.stat().st_size > 0


def test_import_audio_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.audio import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "import_audio.jsfl").read_text(encoding="utf-8")
    for placeholder in [
        "{{FLA_PATH}}", "{{AUDIO_PATH}}", "{{LAYER_NAME}}",
        "{{FRAME}}", "{{SENTINEL_PATH}}",
    ]:
        assert placeholder in content, f"missing {placeholder}"


def test_set_switch_state_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.audio import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "set_switch_state.jsfl").read_text(encoding="utf-8")
    for placeholder in [
        "{{FLA_PATH}}", "{{LAYER_NAME}}", "{{FRAME}}",
        "{{STATE_NAME}}", "{{SENTINEL_PATH}}",
    ]:
        assert placeholder in content, f"missing {placeholder}"


def test_apply_auto_lipsync_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.audio import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "apply_auto_lipsync.jsfl").read_text(encoding="utf-8")
    for placeholder in [
        "{{FLA_PATH}}", "{{AUDIO_LAYER}}",
        "{{MOUTH_LAYER}}", "{{SENTINEL_PATH}}",
    ]:
        assert placeholder in content, f"missing {placeholder}"


def test_dispatcher_has_all_phase3h_handlers():
    from animate_cc_pipeline.mcp_server.server import TOOL_HANDLERS

    for name in ["import_audio", "set_switch_state", "apply_auto_lipsync"]:
        assert name in TOOL_HANDLERS


def test_import_audio_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import audio

    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"RIFF")  # not a real WAV but exists

    result = asyncio.run(audio.handle_import_audio({
        "fla_path": str(tmp_path / "missing.fla"),
        "audio_path": str(audio_file),
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_import_audio_rejects_missing_audio_file(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import audio

    fla = tmp_path / "exists.fla"
    fla.write_bytes(b"\x00")

    result = asyncio.run(audio.handle_import_audio({
        "fla_path": str(fla),
        "audio_path": str(tmp_path / "missing.wav"),
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "audio_path does not exist" in payload["error"]


def test_set_switch_state_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import audio

    result = asyncio.run(audio.handle_set_switch_state({
        "fla_path": str(tmp_path / "missing.fla"),
        "layer_name": "MOUTH",
        "state_name": "mouth_A",
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_apply_auto_lipsync_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import audio

    result = asyncio.run(audio.handle_apply_auto_lipsync({
        "fla_path": str(tmp_path / "missing.fla"),
        "audio_layer": "AUDIO",
        "mouth_layer": "MOUTH",
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"


def test_phase3h_tool_descriptions_non_empty():
    from animate_cc_pipeline.mcp_server.tools.audio import ALL_TOOLS

    for tool in ALL_TOOLS:
        assert tool.description
        assert len(tool.description) >= 30


def test_phase3h_tool_schemas_strict():
    from animate_cc_pipeline.mcp_server.tools.audio import ALL_TOOLS

    for tool in ALL_TOOLS:
        assert tool.inputSchema.get("additionalProperties") is False


def test_total_tool_count_phase3h():
    """1 ping + 5 doc + 4 symbol + 4 keyframe + 3 bone + 3 tween + 3 audio = 23."""
    names = _all_tool_names()
    assert len(names) >= 23, f"expected >=23 tools, got {sorted(names)}"


def test_import_audio_default_layer_name():
    """Schema default for layer_name should be 'AUDIO'."""
    from animate_cc_pipeline.mcp_server.tools.audio import IMPORT_AUDIO_TOOL

    layer_default = IMPORT_AUDIO_TOOL.inputSchema["properties"]["layer_name"].get("default")
    assert layer_default == "AUDIO"


def test_apply_auto_lipsync_marked_experimental():
    """The tool description must communicate the experimental status."""
    from animate_cc_pipeline.mcp_server.tools.audio import APPLY_AUTO_LIPSYNC_TOOL

    desc = APPLY_AUTO_LIPSYNC_TOOL.description.lower()
    assert "experimental" in desc
