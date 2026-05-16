"""Unit tests for Phase 3g tween tools.

No Animate.exe spawn. Covers tool registration, JSFL templates,
arg validation, dispatcher routing.

Run via:
    <python> -m pytest animate_cc_pipeline/tests/test_tween_tools.py -v
"""

from __future__ import annotations

import asyncio
import json

import pytest


def _all_tool_names():
    from animate_cc_pipeline.mcp_server.server import handle_list_tools

    tools = asyncio.run(handle_list_tools())
    return {t.name for t in tools}


def test_server_lists_all_phase3g_tools():
    expected = {"add_classic_tween", "add_motion_tween", "set_easing"}
    assert _all_tool_names() >= expected


def test_server_version_at_least_0_6():
    from animate_cc_pipeline.mcp_server.server import SERVER_VERSION

    major, minor = (int(p) for p in SERVER_VERSION.split(".")[:2])
    assert (major, minor) >= (0, 6), f"expected >=0.6.x for Phase 3g, got {SERVER_VERSION}"


def test_phase3g_jsfl_templates_exist():
    from animate_cc_pipeline.mcp_server.tools.tween import JSFL_TEMPLATES_DIR

    for name in [
        "add_classic_tween.jsfl",
        "add_motion_tween.jsfl",
        "set_easing.jsfl",
    ]:
        p = JSFL_TEMPLATES_DIR / name
        assert p.exists(), f"missing JSFL template: {p}"
        assert p.stat().st_size > 0


def test_add_classic_tween_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.tween import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "add_classic_tween.jsfl").read_text(encoding="utf-8")
    for placeholder in ["{{FLA_PATH}}", "{{LAYER_NAME}}", "{{START_FRAME}}", "{{SENTINEL_PATH}}"]:
        assert placeholder in content


def test_add_motion_tween_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.tween import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "add_motion_tween.jsfl").read_text(encoding="utf-8")
    for placeholder in [
        "{{FLA_PATH}}", "{{LAYER_NAME}}",
        "{{START_FRAME}}", "{{END_FRAME}}", "{{SENTINEL_PATH}}",
    ]:
        assert placeholder in content


def test_set_easing_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.tween import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "set_easing.jsfl").read_text(encoding="utf-8")
    for placeholder in [
        "{{FLA_PATH}}", "{{LAYER_NAME}}", "{{FRAME}}",
        "{{EASING}}", "{{SENTINEL_PATH}}",
    ]:
        assert placeholder in content


def test_dispatcher_has_all_phase3g_handlers():
    from animate_cc_pipeline.mcp_server.server import TOOL_HANDLERS

    for name in ["add_classic_tween", "add_motion_tween", "set_easing"]:
        assert name in TOOL_HANDLERS


def test_add_classic_tween_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import tween

    result = asyncio.run(tween.handle_add_classic_tween({
        "fla_path": str(tmp_path / "missing.fla"),
        "layer_name": "BG",
        "start_frame": 1,
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_add_motion_tween_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import tween

    result = asyncio.run(tween.handle_add_motion_tween({
        "fla_path": str(tmp_path / "missing.fla"),
        "layer_name": "BG",
        "start_frame": 1,
        "end_frame": 30,
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"


def test_add_motion_tween_rejects_invalid_range(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import tween

    fla = tmp_path / "exists.fla"
    fla.write_bytes(b"\x00")
    result = asyncio.run(tween.handle_add_motion_tween({
        "fla_path": str(fla),
        "layer_name": "BG",
        "start_frame": 30,
        "end_frame": 1,  # end <= start
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "end_frame" in payload["error"]


def test_set_easing_rejects_out_of_range(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import tween

    fla = tmp_path / "exists.fla"
    fla.write_bytes(b"\x00")
    for bad in [-101, 101, 200, -200]:
        result = asyncio.run(tween.handle_set_easing({
            "fla_path": str(fla),
            "layer_name": "BG",
            "frame": 1,
            "easing": bad,
        }))
        payload = json.loads(result[0].text)
        assert payload["status"] == "error", f"easing={bad} should have been rejected"


def test_set_easing_accepts_boundary_values(tmp_path, monkeypatch):
    """easing=-100, 0, 100 should pass validation (Animate not actually launched here)."""
    from animate_cc_pipeline.mcp_server.tools import tween

    # Provide a fla file so file-exists check passes. We use monkeypatch
    # to make the JSFL bridge a no-op so we don't actually launch
    # Animate during this unit test.
    fla = tmp_path / "exists.fla"
    fla.write_bytes(b"\x00")

    from animate_cc_pipeline.mcp_server import jsfl_bridge

    def fake_run(template_path, substitutions, expected_outputs, **kwargs):
        for p in expected_outputs:
            p.write_text("done")
        return jsfl_bridge.JsflResult(
            completed_normally=True,
            exit_code=0,
            elapsed_seconds=0.01,
            rendered_script="// fake",
            jsfl_path=str(template_path),
        )
    monkeypatch.setattr(jsfl_bridge, "run_jsfl_template", fake_run)

    for ok_val in [-100, 0, 100, -50, 75]:
        result = asyncio.run(tween.handle_set_easing({
            "fla_path": str(fla),
            "layer_name": "BG",
            "frame": 1,
            "easing": ok_val,
        }))
        payload = json.loads(result[0].text)
        assert payload["status"] == "ok", (
            f"easing={ok_val} should be accepted; got {payload}"
        )


def test_set_easing_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import tween

    result = asyncio.run(tween.handle_set_easing({
        "fla_path": str(tmp_path / "missing.fla"),
        "layer_name": "BG",
        "frame": 1,
        "easing": 0,
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"


def test_phase3g_tool_descriptions_non_empty():
    from animate_cc_pipeline.mcp_server.tools.tween import ALL_TOOLS

    for tool in ALL_TOOLS:
        assert tool.description
        assert len(tool.description) >= 30


def test_phase3g_tool_schemas_strict():
    from animate_cc_pipeline.mcp_server.tools.tween import ALL_TOOLS

    for tool in ALL_TOOLS:
        assert tool.inputSchema.get("additionalProperties") is False


def test_total_tool_count_phase3g():
    """1 ping + 5 doc + 4 symbol + 4 keyframe + 3 bone + 3 tween = 20."""
    names = _all_tool_names()
    assert len(names) >= 20, f"expected >=20 tools, got {sorted(names)}"
