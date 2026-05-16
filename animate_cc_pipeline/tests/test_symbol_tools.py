"""Unit tests for Phase 3d symbol-placement tools.

No Animate.exe spawn — these tests verify:
  - Tool registration in server's catalog
  - JSFL template files exist with required placeholders
  - Argument validation (missing required fields, missing fla_path)
  - Handler dispatch routing

Run via:
    <python> -m pytest animate_cc_pipeline/tests/test_symbol_tools.py -v
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


def test_server_lists_all_phase3d_tools():
    expected = {
        "place_symbol_instance",
        "set_instance_position",
        "set_instance_scale",
        "set_instance_rotation",
    }
    assert _all_tool_names() >= expected


def test_server_version_at_least_0_3():
    """Phase 3d bumped to >=0.3. Forward-compatible across later
    phase bumps (same convention as the 0.2 guard from Phase 3c).
    """
    from animate_cc_pipeline.mcp_server.server import SERVER_VERSION

    parts = SERVER_VERSION.split(".")
    major, minor = int(parts[0]), int(parts[1])
    assert (major, minor) >= (0, 3), (
        f"expected >=0.3.x for Phase 3d+, got {SERVER_VERSION}"
    )


def test_phase3d_jsfl_templates_exist():
    from animate_cc_pipeline.mcp_server.tools.symbol import JSFL_TEMPLATES_DIR

    for name in [
        "place_symbol_instance.jsfl",
        "set_instance_position.jsfl",
        "set_instance_scale.jsfl",
        "set_instance_rotation.jsfl",
    ]:
        p = JSFL_TEMPLATES_DIR / name
        assert p.exists(), f"missing JSFL template: {p}"
        assert p.stat().st_size > 0, f"empty JSFL template: {p}"


def test_place_symbol_instance_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.symbol import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "place_symbol_instance.jsfl").read_text(encoding="utf-8")
    for placeholder in [
        "{{FLA_PATH}}", "{{SYMBOL_NAME}}", "{{LAYER_NAME}}",
        "{{FRAME}}", "{{X}}", "{{Y}}", "{{SENTINEL_PATH}}",
    ]:
        assert placeholder in content, f"place_symbol_instance.jsfl missing {placeholder}"


def test_set_instance_position_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.symbol import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "set_instance_position.jsfl").read_text(encoding="utf-8")
    for placeholder in ["{{FLA_PATH}}", "{{LAYER_NAME}}", "{{FRAME}}", "{{X}}", "{{Y}}", "{{SENTINEL_PATH}}"]:
        assert placeholder in content, f"set_instance_position.jsfl missing {placeholder}"


def test_set_instance_scale_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.symbol import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "set_instance_scale.jsfl").read_text(encoding="utf-8")
    for placeholder in ["{{FLA_PATH}}", "{{LAYER_NAME}}", "{{FRAME}}", "{{SX}}", "{{SY}}", "{{SENTINEL_PATH}}"]:
        assert placeholder in content, f"set_instance_scale.jsfl missing {placeholder}"


def test_set_instance_rotation_template_placeholders():
    from animate_cc_pipeline.mcp_server.tools.symbol import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "set_instance_rotation.jsfl").read_text(encoding="utf-8")
    for placeholder in ["{{FLA_PATH}}", "{{LAYER_NAME}}", "{{FRAME}}", "{{ANGLE}}", "{{SENTINEL_PATH}}"]:
        assert placeholder in content, f"set_instance_rotation.jsfl missing {placeholder}"


def test_dispatcher_has_all_phase3d_handlers():
    from animate_cc_pipeline.mcp_server.server import TOOL_HANDLERS

    for name in [
        "place_symbol_instance",
        "set_instance_position",
        "set_instance_scale",
        "set_instance_rotation",
    ]:
        assert name in TOOL_HANDLERS, f"missing handler: {name}"


# ─── Argument validation (no Animate spawn) ─────────────────────────


def test_place_symbol_instance_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import symbol

    result = asyncio.run(symbol.handle_place_symbol_instance({
        "fla_path": str(tmp_path / "missing.fla"),
        "symbol_name": "X",
        "layer_name": "L1",
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_set_instance_position_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import symbol

    result = asyncio.run(symbol.handle_set_instance_position({
        "fla_path": str(tmp_path / "missing.fla"),
        "layer_name": "L1",
        "x": 100,
        "y": 200,
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_set_instance_scale_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import symbol

    result = asyncio.run(symbol.handle_set_instance_scale({
        "fla_path": str(tmp_path / "missing.fla"),
        "layer_name": "L1",
        "sx": 1.5,
        "sy": 1.5,
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_set_instance_rotation_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import symbol

    result = asyncio.run(symbol.handle_set_instance_rotation({
        "fla_path": str(tmp_path / "missing.fla"),
        "layer_name": "L1",
        "angle": 45,
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_phase3d_tool_descriptions_non_empty():
    from animate_cc_pipeline.mcp_server.tools.symbol import ALL_TOOLS

    for tool in ALL_TOOLS:
        assert tool.description, f"{tool.name} has no description"
        assert len(tool.description) >= 30, f"{tool.name} description too short"


def test_phase3d_tool_schemas_strict():
    from animate_cc_pipeline.mcp_server.tools.symbol import ALL_TOOLS

    for tool in ALL_TOOLS:
        assert tool.inputSchema.get("additionalProperties") is False, (
            f"{tool.name} must set additionalProperties=False"
        )


def test_total_server_tool_count_phase3d():
    """Phase 3d brings us to: 1 ping + 5 document + 4 symbol = 10 tools."""
    names = _all_tool_names()
    assert len(names) >= 10, f"expected >=10 tools, got {sorted(names)}"
