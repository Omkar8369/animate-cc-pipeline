"""MCP tool categories for the Animate CC Pipeline.

Each submodule defines a group of related MCP tools and exposes:
  - ``ALL_TOOLS``: list of ``mcp.types.Tool`` definitions
  - ``TOOL_HANDLERS``: dict mapping tool name → async handler

``server.py`` aggregates these to build the full server tool catalog.
"""
