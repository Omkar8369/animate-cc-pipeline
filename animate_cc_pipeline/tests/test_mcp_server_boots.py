"""Unit tests for the MCP server.

These tests do NOT spawn Animate.exe. They exercise the Python-side
MCP server only: module imports, tool catalog, ``ping`` response,
unknown-tool error.

Run via:
    <python> -m pytest animate_cc_pipeline/tests/test_mcp_server_boots.py -v
"""

from __future__ import annotations

import asyncio
import json

import pytest


def test_module_imports_cleanly():
    """The server module imports without error (mcp must be installed)."""
    from animate_cc_pipeline.mcp_server import server as srv

    assert srv.SERVER_NAME == "animate-cc"
    assert srv.SERVER_VERSION
    assert callable(srv.main)
    assert callable(srv.amain)


def test_ping_tool_is_listed():
    """``list_tools`` returns the ping tool with a well-formed schema."""
    from animate_cc_pipeline.mcp_server.server import handle_list_tools

    tools = asyncio.run(handle_list_tools())

    assert isinstance(tools, list)
    assert len(tools) >= 1

    ping_tools = [t for t in tools if t.name == "ping"]
    assert len(ping_tools) == 1, "expected exactly one ping tool"

    ping = ping_tools[0]
    assert ping.description, "ping must have a description"
    assert ping.inputSchema["type"] == "object"
    assert ping.inputSchema["additionalProperties"] is False


def test_ping_responds_with_status_ok():
    """Calling ``ping`` returns valid JSON with status=ok."""
    from animate_cc_pipeline.mcp_server.server import handle_call_tool

    result = asyncio.run(handle_call_tool("ping", {}))

    assert isinstance(result, list)
    assert len(result) == 1

    payload = json.loads(result[0].text)
    assert payload["status"] == "ok"
    assert payload["server_name"] == "animate-cc"
    assert "server_version" in payload
    assert "animate_cc_exe" in payload


def test_ping_with_none_arguments():
    """``ping`` accepts ``None`` arguments (treated as empty dict)."""
    from animate_cc_pipeline.mcp_server.server import handle_call_tool

    result = asyncio.run(handle_call_tool("ping", None))
    payload = json.loads(result[0].text)
    assert payload["status"] == "ok"


def test_unknown_tool_raises_value_error():
    """Calling an unregistered tool raises ``ValueError``."""
    from animate_cc_pipeline.mcp_server.server import handle_call_tool

    with pytest.raises(ValueError, match="Unknown tool"):
        asyncio.run(handle_call_tool("nonexistent_tool", {}))


def test_default_animate_exe_constant():
    """``DEFAULT_ANIMATE_CC_EXE`` points at a sensible path string."""
    from animate_cc_pipeline.mcp_server.server import DEFAULT_ANIMATE_CC_EXE

    assert "Animate.exe" in DEFAULT_ANIMATE_CC_EXE
    assert "Adobe" in DEFAULT_ANIMATE_CC_EXE
