"""Unit tests for the Phase 3c document tools.

No Animate.exe spawn — these tests verify:
  - Tool catalog registration (server lists all 6 tools)
  - JSFL template files exist with required placeholders
  - Tool dispatcher routes by name correctly
  - Argument validation (missing required, bad paths)
  - close_document path (which doesn't spawn Animate)

The actual Animate-spawning integration test lives in
``_smoke_phase3c.py``.

Run via:
    <python> -m pytest animate_cc_pipeline/tests/test_document_tools.py -v
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


def test_server_lists_all_phase3c_tools():
    expected = {
        "ping",
        "create_document",
        "save_document",
        "close_document",
        "import_image_as_layer",
        "import_video_as_layer",
    }
    assert _all_tool_names() >= expected


def test_server_version_bumped_for_phase3c():
    from animate_cc_pipeline.mcp_server.server import SERVER_VERSION
    # Phase 3c bumps to 0.2.x
    assert SERVER_VERSION.startswith("0.2"), (
        f"expected version 0.2.x for Phase 3c, got {SERVER_VERSION}"
    )


def test_all_jsfl_templates_exist():
    from animate_cc_pipeline.mcp_server.tools.document import JSFL_TEMPLATES_DIR

    expected_files = [
        "create_doc.jsfl",
        "save_doc.jsfl",
        "import_image.jsfl",
        "import_video.jsfl",
        "hello_world.jsfl",  # Phase 3b, still present
    ]
    for name in expected_files:
        p = JSFL_TEMPLATES_DIR / name
        assert p.exists(), f"missing JSFL template: {p}"
        assert p.stat().st_size > 0, f"empty JSFL template: {p}"


def test_create_doc_template_has_required_placeholders():
    from animate_cc_pipeline.mcp_server.tools.document import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "create_doc.jsfl").read_text(encoding="utf-8")
    for placeholder in ["{{FLA_PATH}}", "{{SENTINEL_PATH}}", "{{WIDTH}}", "{{HEIGHT}}", "{{FPS}}"]:
        assert placeholder in content, f"create_doc.jsfl missing {placeholder}"


def test_import_image_template_has_required_placeholders():
    from animate_cc_pipeline.mcp_server.tools.document import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "import_image.jsfl").read_text(encoding="utf-8")
    for placeholder in ["{{FLA_PATH}}", "{{IMAGE_PATH}}", "{{LAYER_NAME}}", "{{FRAME}}", "{{SENTINEL_PATH}}"]:
        assert placeholder in content, f"import_image.jsfl missing {placeholder}"


def test_import_video_template_has_required_placeholders():
    from animate_cc_pipeline.mcp_server.tools.document import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "import_video.jsfl").read_text(encoding="utf-8")
    for placeholder in ["{{FLA_PATH}}", "{{MP4_PATH}}", "{{LAYER_NAME}}", "{{FRAME}}", "{{SENTINEL_PATH}}"]:
        assert placeholder in content, f"import_video.jsfl missing {placeholder}"


def test_save_doc_template_has_required_placeholders():
    from animate_cc_pipeline.mcp_server.tools.document import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "save_doc.jsfl").read_text(encoding="utf-8")
    for placeholder in ["{{FLA_PATH}}", "{{SENTINEL_PATH}}"]:
        assert placeholder in content, f"save_doc.jsfl missing {placeholder}"


def test_dispatcher_has_all_handlers():
    """server.TOOL_HANDLERS must have an entry for every non-ping tool."""
    from animate_cc_pipeline.mcp_server.server import TOOL_HANDLERS

    expected_handler_names = {
        "create_document",
        "save_document",
        "close_document",
        "import_image_as_layer",
        "import_video_as_layer",
    }
    assert set(TOOL_HANDLERS) >= expected_handler_names


def test_unknown_tool_still_raises():
    """Phase 3b's unknown-tool error semantics must survive Phase 3c."""
    from animate_cc_pipeline.mcp_server.server import handle_call_tool

    with pytest.raises(ValueError, match="Unknown tool"):
        asyncio.run(handle_call_tool("nonexistent", {}))


# ─── close_document (no Animate spawn) ──────────────────────────────


def test_close_document_when_animate_not_running(monkeypatch):
    """close_document returns killed=false when Animate isn't running."""
    from animate_cc_pipeline.mcp_server.tools import document
    from animate_cc_pipeline.mcp_server import jsfl_bridge

    monkeypatch.setattr(jsfl_bridge, "_animate_running", lambda: False)
    monkeypatch.setattr(jsfl_bridge, "_kill_animate", lambda *a, **k: pytest.fail(
        "_kill_animate should NOT be called when Animate isn't running"
    ))

    result = asyncio.run(document.handle_close_document({}))
    payload = json.loads(result[0].text)
    assert payload == {"status": "ok", "killed": False}


def test_close_document_kills_when_running(monkeypatch):
    from animate_cc_pipeline.mcp_server.tools import document
    from animate_cc_pipeline.mcp_server import jsfl_bridge

    called = {"killed": False}
    monkeypatch.setattr(jsfl_bridge, "_animate_running", lambda: True)
    monkeypatch.setattr(jsfl_bridge, "_kill_animate", lambda *a, **k: called.update(killed=True))

    result = asyncio.run(document.handle_close_document(None))
    payload = json.loads(result[0].text)
    assert payload == {"status": "ok", "killed": True}
    assert called["killed"] is True


# ─── Argument validation (no Animate spawn) ─────────────────────────


def test_save_document_rejects_missing_file(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import document

    missing = tmp_path / "does_not_exist.fla"
    result = asyncio.run(document.handle_save_document({"fla_path": str(missing)}))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_import_image_rejects_missing_image(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import document

    fla = tmp_path / "exists.fla"
    fla.write_bytes(b"\x00\x01\x02")  # fake .fla; tool doesn't actually open here
    missing_image = tmp_path / "missing.png"

    result = asyncio.run(document.handle_import_image_as_layer({
        "fla_path": str(fla),
        "image_path": str(missing_image),
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "image_path does not exist" in payload["error"]


def test_import_video_rejects_missing_video(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import document

    fla = tmp_path / "exists.fla"
    fla.write_bytes(b"\x00\x01")
    missing = tmp_path / "missing.mp4"

    result = asyncio.run(document.handle_import_video_as_layer({
        "fla_path": str(fla),
        "mp4_path": str(missing),
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "mp4_path does not exist" in payload["error"]


def test_tool_descriptions_are_non_empty():
    """Every Phase 3c tool must have a description for Claude."""
    from animate_cc_pipeline.mcp_server.tools.document import ALL_TOOLS

    for tool in ALL_TOOLS:
        assert tool.description, f"{tool.name} has no description"
        assert len(tool.description) >= 30, f"{tool.name} description too short"


def test_tool_input_schemas_are_strict():
    """All Phase 3c tool input schemas reject extra properties."""
    from animate_cc_pipeline.mcp_server.tools.document import ALL_TOOLS

    for tool in ALL_TOOLS:
        assert tool.inputSchema.get("additionalProperties") is False, (
            f"{tool.name} inputSchema must set additionalProperties=False"
        )


def test_to_jsfl_path_normalizes_backslashes():
    from animate_cc_pipeline.mcp_server.tools.document import _to_jsfl_path

    assert _to_jsfl_path(r"C:\foo\bar.fla") == "C:/foo/bar.fla"
    assert _to_jsfl_path("C:/already/forward.fla") == "C:/already/forward.fla"
    assert _to_jsfl_path(Path(r"C:\path\to\file")) in (
        "C:/path/to/file",  # if Path.__str__ returns backslashes
    )
