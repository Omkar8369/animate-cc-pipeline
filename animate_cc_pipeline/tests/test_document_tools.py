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
        # Phase 3o-code addition
        "import_character_rig",
    }
    assert _all_tool_names() >= expected


def test_server_version_at_least_0_2():
    """Phase 3c bumped to >=0.2. Later phases keep bumping; this test
    just guards against accidental regression to 0.1 or pre-3c state.
    """
    from animate_cc_pipeline.mcp_server.server import SERVER_VERSION

    parts = SERVER_VERSION.split(".")
    major = int(parts[0])
    minor = int(parts[1])
    assert (major, minor) >= (0, 2), (
        f"expected >=0.2.x for Phase 3c+, got {SERVER_VERSION}"
    )


def test_all_jsfl_templates_exist():
    from animate_cc_pipeline.mcp_server.tools.document import JSFL_TEMPLATES_DIR

    expected_files = [
        "create_doc.jsfl",
        "save_doc.jsfl",
        "import_image.jsfl",
        "import_video.jsfl",
        "import_character_rig.jsfl",  # Phase 3o-code
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


def test_import_character_rig_template_has_required_placeholders():
    from animate_cc_pipeline.mcp_server.tools.document import JSFL_TEMPLATES_DIR

    content = (JSFL_TEMPLATES_DIR / "import_character_rig.jsfl").read_text(encoding="utf-8")
    for placeholder in [
        "{{FLA_PATH}}", "{{RIG_FLA_PATH}}", "{{IDENTITY}}", "{{LAYER_NAME}}",
        "{{FRAME}}", "{{X}}", "{{Y}}", "{{SENTINEL_PATH}}",
    ]:
        assert placeholder in content, f"import_character_rig.jsfl missing {placeholder}"


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
        "import_character_rig",  # Phase 3o-code
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


# ─── import_character_rig (Phase 3o-code) ──────────────────────────


def _fake_jsfl_result(completed: bool, missing: list[Path] | None = None):
    """Build a JsflResult-like stand-in for monkeypatching."""
    from animate_cc_pipeline.mcp_server.jsfl_bridge import JsflResult
    return JsflResult(
        completed_normally=completed,
        exit_code=None,
        elapsed_seconds=1.5,
        rendered_script="// mocked",
        jsfl_path="(mocked)",
        missing_outputs=missing or [],
    )


def test_import_character_rig_rejects_missing_fla(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import document

    rig = tmp_path / "rig.fla"
    rig.write_bytes(b"\x00\x01")
    result = asyncio.run(document.handle_import_character_rig({
        "fla_path": str(tmp_path / "missing.fla"),
        "rig_fla_path": str(rig),
        "identity": "JETHALAL",
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "fla_path does not exist" in payload["error"]


def test_import_character_rig_rejects_missing_rig(tmp_path):
    from animate_cc_pipeline.mcp_server.tools import document

    fla = tmp_path / "target.fla"
    fla.write_bytes(b"\x00\x01")
    result = asyncio.run(document.handle_import_character_rig({
        "fla_path": str(fla),
        "rig_fla_path": str(tmp_path / "missing_rig.fla"),
        "identity": "JETHALAL",
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "rig_fla_path does not exist" in payload["error"]


def test_import_character_rig_success_path(monkeypatch, tmp_path):
    """Mock the JSFL bridge to simulate a successful rig import."""
    from animate_cc_pipeline.mcp_server.tools import document
    from animate_cc_pipeline.mcp_server import jsfl_bridge

    fla = tmp_path / "target.fla"
    fla.write_bytes(b"\x00\x01")
    rig = tmp_path / "rig.fla"
    rig.write_bytes(b"\x00\x01")

    # The handler reads the sentinel BEFORE unlinking; simulate the
    # JSFL writing "done" by intercepting run_jsfl_template and
    # writing the sentinel ourselves.
    def fake_run(template, substitutions, expected_outputs, poll_timeout=180.0):
        sentinel = Path(substitutions["SENTINEL_PATH"])
        sentinel.write_text("done", encoding="utf-8")
        return _fake_jsfl_result(completed=True)

    monkeypatch.setattr(jsfl_bridge, "run_jsfl_template", fake_run)

    result = asyncio.run(document.handle_import_character_rig({
        "fla_path": str(fla),
        "rig_fla_path": str(rig),
        "identity": "JETHALAL",
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "ok"
    assert payload["identity"] == "JETHALAL"
    assert payload["layer_name"] == "JETHALAL"
    assert payload["instance_placed"] is True


def test_import_character_rig_layer_name_defaults_to_identity(monkeypatch, tmp_path):
    from animate_cc_pipeline.mcp_server.tools import document
    from animate_cc_pipeline.mcp_server import jsfl_bridge

    fla = tmp_path / "target.fla"; fla.write_bytes(b"\x00")
    rig = tmp_path / "rig.fla"; rig.write_bytes(b"\x00")

    captured: dict = {}

    def fake_run(template, substitutions, expected_outputs, poll_timeout=180.0):
        captured.update(substitutions)
        Path(substitutions["SENTINEL_PATH"]).write_text("done", encoding="utf-8")
        return _fake_jsfl_result(completed=True)

    monkeypatch.setattr(jsfl_bridge, "run_jsfl_template", fake_run)

    asyncio.run(document.handle_import_character_rig({
        "fla_path": str(fla),
        "rig_fla_path": str(rig),
        "identity": "TAPPU",
        # no layer_name → should default to "TAPPU"
    }))
    assert captured["LAYER_NAME"] == "TAPPU"


def test_import_character_rig_jsfl_import_failed(monkeypatch, tmp_path):
    """Sentinel content 'import_failed' → handler returns error."""
    from animate_cc_pipeline.mcp_server.tools import document
    from animate_cc_pipeline.mcp_server import jsfl_bridge

    fla = tmp_path / "target.fla"; fla.write_bytes(b"\x00")
    rig = tmp_path / "rig.fla"; rig.write_bytes(b"\x00")

    def fake_run(template, substitutions, expected_outputs, poll_timeout=180.0):
        Path(substitutions["SENTINEL_PATH"]).write_text("import_failed", encoding="utf-8")
        return _fake_jsfl_result(completed=True)

    monkeypatch.setattr(jsfl_bridge, "run_jsfl_template", fake_run)

    result = asyncio.run(document.handle_import_character_rig({
        "fla_path": str(fla),
        "rig_fla_path": str(rig),
        "identity": "JETHALAL",
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "importFile returned false" in payload["error"]


def test_import_character_rig_instance_not_placed(monkeypatch, tmp_path):
    """Sentinel 'instance_not_placed' → status=ok but instance_placed=false + warning."""
    from animate_cc_pipeline.mcp_server.tools import document
    from animate_cc_pipeline.mcp_server import jsfl_bridge

    fla = tmp_path / "target.fla"; fla.write_bytes(b"\x00")
    rig = tmp_path / "rig.fla"; rig.write_bytes(b"\x00")

    def fake_run(template, substitutions, expected_outputs, poll_timeout=180.0):
        Path(substitutions["SENTINEL_PATH"]).write_text("instance_not_placed", encoding="utf-8")
        return _fake_jsfl_result(completed=True)

    monkeypatch.setattr(jsfl_bridge, "run_jsfl_template", fake_run)

    result = asyncio.run(document.handle_import_character_rig({
        "fla_path": str(fla),
        "rig_fla_path": str(rig),
        "identity": "MYSTERY",
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "ok"
    assert payload["instance_placed"] is False
    assert "warning" in payload


def test_import_character_rig_jsfl_did_not_complete(monkeypatch, tmp_path):
    """If the bridge times out, handler returns error."""
    from animate_cc_pipeline.mcp_server.tools import document
    from animate_cc_pipeline.mcp_server import jsfl_bridge

    fla = tmp_path / "target.fla"; fla.write_bytes(b"\x00")
    rig = tmp_path / "rig.fla"; rig.write_bytes(b"\x00")

    def fake_run(template, substitutions, expected_outputs, poll_timeout=180.0):
        # Don't write the sentinel — JSFL "didn't complete"
        return _fake_jsfl_result(completed=False, missing=expected_outputs)

    monkeypatch.setattr(jsfl_bridge, "run_jsfl_template", fake_run)

    result = asyncio.run(document.handle_import_character_rig({
        "fla_path": str(fla),
        "rig_fla_path": str(rig),
        "identity": "JETHALAL",
    }))
    payload = json.loads(result[0].text)
    assert payload["status"] == "error"
    assert "did not complete" in payload["error"]


def test_import_character_rig_inputschema_requires_identity():
    """The JSON schema must mark identity, fla_path, rig_fla_path as required."""
    from animate_cc_pipeline.mcp_server.tools.document import IMPORT_CHARACTER_RIG_TOOL

    required = set(IMPORT_CHARACTER_RIG_TOOL.inputSchema.get("required", []))
    assert {"fla_path", "rig_fla_path", "identity"} <= required
