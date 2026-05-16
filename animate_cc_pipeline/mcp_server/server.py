"""MCP server for the Animate CC Pipeline.

Phase 3b scope: exposes ONE tool (``ping``) for health checking. Real
Animate-CC tools (document, symbol, keyframe, bone, tween, audio,
camera, render) ship in Phases 3c-3i.

Run directly:

    <python> -m animate_cc_pipeline.mcp_server.server

Claude Code auto-launches this server based on ``.claude/settings.json``
(plus ``settings.local.json`` overrides written by
``tools/phase3/setup_local_python.py``). Communication is over stdio
per MCP convention; this process must not write anything to stdout
that isn't MCP protocol (all logging goes to stderr).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

# ─── MCP imports ────────────────────────────────────────────────────
# Defer with a clear error message so a missing dep doesn't show up
# as an opaque ImportError to Claude Code.
try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server
    import mcp.types as types
except ImportError as exc:  # pragma: no cover - exercised at runtime only
    print(
        "ERROR: 'mcp' package not installed.\n"
        "Install via:  <python> -m pip install -r requirements.txt\n"
        f"Original error: {exc}",
        file=sys.stderr,
    )
    raise


# ─── Server metadata ────────────────────────────────────────────────

SERVER_NAME = "animate-cc"
SERVER_VERSION = "0.6.0"  # Phase 3g: tween tools

DEFAULT_ANIMATE_CC_EXE = (
    r"C:\Program Files\Adobe\Adobe Animate 2020\Animate.exe"
)

logger = logging.getLogger("animate_cc_mcp")


# ─── Tool category imports ──────────────────────────────────────────
# Each tools/* module exposes ALL_TOOLS + TOOL_HANDLERS that we
# aggregate here.

from .tools import document as document_tools
from .tools import symbol as symbol_tools
from .tools import keyframe as keyframe_tools
from .tools import bone as bone_tools
from .tools import tween as tween_tools


# ─── Tool catalog ───────────────────────────────────────────────────

PING_TOOL = types.Tool(
    name="ping",
    description=(
        "Health check for the animate-cc MCP server. Returns a JSON "
        "object {status, server_name, server_version, animate_cc_exe}. "
        "Call this first to verify the server is reachable before "
        "calling any other tool. Does NOT spawn Animate.exe — pure "
        "Python-side check."
    ),
    inputSchema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
)


# Aggregate tool catalog from all categories
ALL_TOOLS: list[types.Tool] = (
    [PING_TOOL]
    + document_tools.ALL_TOOLS
    + symbol_tools.ALL_TOOLS
    + keyframe_tools.ALL_TOOLS
    + bone_tools.ALL_TOOLS
    + tween_tools.ALL_TOOLS
)

# Aggregate tool handler dispatch table
TOOL_HANDLERS: dict[str, Any] = {
    **document_tools.TOOL_HANDLERS,
    **symbol_tools.TOOL_HANDLERS,
    **keyframe_tools.TOOL_HANDLERS,
    **bone_tools.TOOL_HANDLERS,
    **tween_tools.TOOL_HANDLERS,
    # ping is handled inline (see handle_call_tool); not async-wrapped
}


# ─── Server wiring ──────────────────────────────────────────────────

server = Server(SERVER_NAME)


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Return the catalog of tools this server exposes."""
    return list(ALL_TOOLS)


@server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: dict[str, Any] | None,
) -> list[types.TextContent]:
    """Dispatch a tool call to its handler."""
    if name == "ping":
        return _handle_ping()
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name!r}")
    return await handler(arguments)


def _handle_ping() -> list[types.TextContent]:
    payload = {
        "status": "ok",
        "server_name": SERVER_NAME,
        "server_version": SERVER_VERSION,
        "animate_cc_exe": os.environ.get(
            "ANIMATE_CC_EXE", DEFAULT_ANIMATE_CC_EXE
        ),
        "log_level": os.environ.get("ANIMATE_LOG_LEVEL", "info"),
    }
    return [types.TextContent(type="text", text=json.dumps(payload))]


# ─── Entry point ────────────────────────────────────────────────────

async def amain() -> None:
    """Async main: configure logging, then run the MCP server on stdio."""
    log_level_name = os.environ.get("ANIMATE_LOG_LEVEL", "info").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,  # MCP protocol owns stdout
    )
    logger.info(f"{SERVER_NAME} v{SERVER_VERSION} starting (log level: {log_level_name})")

    async with stdio_server() as (read_stream, write_stream):
        init_options = InitializationOptions(
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
            capabilities=server.get_capabilities(
                notification_options=NotificationOptions(),
                experimental_capabilities={},
            ),
        )
        await server.run(read_stream, write_stream, init_options)


def main() -> None:
    """Sync entry point used by ``python -m animate_cc_pipeline.mcp_server.server``."""
    asyncio.run(amain())


if __name__ == "__main__":
    main()
