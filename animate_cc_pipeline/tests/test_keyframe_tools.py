"""Unit tests for Phase 3e keyframe tools.

No Animate.exe spawn. Covers:
  - Tool registration in server's catalog
  - JSFL template files exist with required placeholders
  - Argument validation (missing required fields, missing fla_path)
  - Handler dispatch routing
  - get_keyframes JSON readback / handling

Run via:
    <python> -m pytest animate_cc_pipeline/tests/test_keyframe_tools.py -v
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


def _all_tool_names():
    from animate_cc_pipeline.mcp_server.server import handle_list_tools

    tools = asyncio.run(handle_list_tools())
    return {t.name for t in tools}


def test_server_lists_all_phase3e_tools():
    expected = {
        "insert_keyframe",
        "insert_blank_keyframe",
        "remove_keyframe",
        "get_keyframes",
    }
    assert _all_tool_names() >= expected


def test_server_version_at_least_0_4():
    from animate_cc_pipeline.mcp_server.server import SERVER_VERSION

    parts = SERVER_VERSION.split(".")
    major, minor = int(parts[0]), int(parts[1])
    assert (major, minor) >= (0, 4), (
        f"expected >=0.4.x for Phase 3e+, got {SERVER_VERSION}"
    )


def test_phase3e_jsfl_templates_exist():
    from animate_cc_pipeline.mcp_server.tools.keyframe import JSFL_TEMPLATES_DIR

    for name in [
        "insert_keyframe.jsfl",
        "insert_blank_keyframe.jsfl",
        "remove_keyframe.jsfl",
        "get_keyframes.jsfl",
    ]:
        p = JSFL_TEMPLATES_DIR / name
        assert p.exists(), f"missing JSFL template: {p}"
        assert p.stat().st_size > 0


def test_insert_keyframe_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.keyframe import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "insert_keyframe.jsfl").read_text(encoding="utf-8")
    for placeholder in ["{{FLA_PATH}}", "{{LAYER_NAME}}", "{{FRAME}}", "{{SENTINEL_PATH}}"]:
        assert placeholder in content


def test_insert_blank_keyframe_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.keyframe import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "insert_blank_keyframe.jsfl").read_text(encoding="utf-8")
    for placeholder in ["{{FLA_PATH}}", "{{LAYER_NAME}}", "{{FRAME}}", "{{SENTINEL_PATH}}"]:
        assert placeholder in content


def test_remove_keyframe_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.keyframe import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "remove_keyframe.jsfl").read_text(encoding="utf-8")
    for placeholder in ["{{FLA_PATH}}", "{{LAYER_NAME}}", "{{FRAME}}", "{{SENTINEL_PATH}}"]:
        assert placeholder in content


def test_get_keyframes_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.keyframe import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "get_keyframes.jsfl").read_text(encoding="utf-8")
    for placeholder in ["{{FLA_PATH}}", "{{LAYER_NAME}}", "{{OUT_JSON_PATH}}", "{{SENTINEL_PATH}}"]:
        assert placeholder in content


def test_dispatcher_has_all_phase3e_handlers():
    from animate_cc_pipeline.mcp_server.server import TOOL_HANDLERS

    for name in ["insert_keyframe", "insert_blank_keyframe", "remove_keyframe", "get_keyframes"]:
        assert name in TOOL_HANDLERS, f"missing handler: {name}"


# ─── Argument validation (no Animate spawn) ─────────────────────────


def test_insert_keyframe_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import keyframe

    result = asyncio.run(keyframe.handle_insert_keyframe({
        "fla_path": str(tmp_path / "missing.fla"),
        "layer_name": "BG",
        "frame": 10,
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_insert_blank_keyframe_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import keyframe

    result = asyncio.run(keyframe.handle_insert_blank_keyframe({
        "fla_path": str(tmp_path / "missing.fla"),
        "layer_name": "BG",
        "frame": 10,
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_remove_keyframe_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import keyframe

    result = asyncio.run(keyframe.handle_remove_keyframe({
        "fla_path": str(tmp_path / "missing.fla"),
        "layer_name": "BG",
        "frame": 10,
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_get_keyframes_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import keyframe

    result = asyncio.run(keyframe.handle_get_keyframes({
        "fla_path": str(tmp_path / "missing.fla"),
        "layer_name": "BG",
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_phase3e_tool_descriptions_non_empty():
    from animate_cc_pipeline.mcp_server.tools.keyframe import ALL_TOOLS

    for tool in ALL_TOOLS:
        assert tool.description
        assert len(tool.description) >= 30


def test_phase3e_tool_schemas_strict():
    from animate_cc_pipeline.mcp_server.tools.keyframe import ALL_TOOLS

    for tool in ALL_TOOLS:
        assert tool.inputSchema.get("additionalProperties") is False


def test_total_server_tool_count_phase3e():
    """1 ping + 5 document + 4 symbol + 4 keyframe = 14 tools."""
    names = _all_tool_names()
    assert len(names) >= 14, f"expected >=14 tools, got {sorted(names)}"


def test_get_keyframes_includes_keyframes_field_when_ok():
    """get_keyframes _ok response must include the keyframes list +
    layer_found flag — the orchestrator depends on this contract."""
    from animate_cc_pipeline.mcp_server.tools.keyframe import _ok
    from animate_cc_pipeline.mcp_server.jsfl_bridge import JsflResult

    fake = JsflResult(
        completed_normally=True,
        exit_code=None,
        elapsed_seconds=15.0,
        rendered_script="// ...",
        jsfl_path="/tmp/x.jsfl",
    )
    payload = json.loads(_ok(fake, Path("/tmp/x.fla"), {
        "layer_name": "BG",
        "layer_found": True,
        "keyframes": [1, 10, 20],
    }))
    assert payload["keyframes"] == [1, 10, 20]
    assert payload["layer_found"] is True
    assert payload["layer_name"] == "BG"
