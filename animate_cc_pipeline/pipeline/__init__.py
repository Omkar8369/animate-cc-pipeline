"""Pipeline Nodes — pure-Python data processing layer.

Companion to the `mcp_server/` package. Where `mcp_server/` exposes
Animate CC operations as MCP tools, `pipeline/` is the data-only
side: take rough-animatic MP4s + metadata, produce per-frame
character bboxes + pose estimates that the orchestrator (Phase 3l)
hands off to the MCP server.

Phase 3j ships Node 6 (per-frame pose estimation). Earlier pipeline
Nodes (Node 2-5) are intentionally NOT in this repo — they reuse
the prior `animatic-refinement` project's implementations directly.
The new pipeline starts at Node 6 because that's where the
animate-cc-pipeline diverges from the prior project's Node 7 (Flux
generation).
"""
