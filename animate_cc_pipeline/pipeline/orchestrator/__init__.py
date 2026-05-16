"""Per-shot orchestrator — the heart of Phase 3l.

Wires together everything we built:
  - MCP tool handlers (Phase 3b-3i) for Animate operations
  - Per-frame pose data (Phase 3j) and pose-to-bone math (Phase 3k)
  - The rig contract from RIG_SPEC_v1

The orchestrator does NOT go through the MCP protocol — it imports
the tool handlers directly and awaits them. The MCP server is the
LLM-facing wrapper; the orchestrator is the deterministic Python
driver that the operator runs in batch.
"""
