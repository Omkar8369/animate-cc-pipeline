"""Tests for the JSFL bridge.

- Unit tests for template rendering + Animate.exe path resolution
  (no subprocess).
- One integration test that actually spawns Animate.exe to create a
  ``.fla``. Gated by:
    * ``SKIP_ANIMATE_TESTS=1`` env var (manual skip)
    * Missing Animate.exe on the machine (auto skip)

Run via:
    <python> -m pytest animate_cc_pipeline/tests/test_jsfl_bridge.py -v
    SKIP_ANIMATE_TESTS=1 <python> -m pytest animate_cc_pipeline/tests/test_jsfl_bridge.py -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


# ─── Unit tests (no subprocess) ─────────────────────────────────────


def test_default_animate_cc_exe_constant():
    from animate_cc_pipeline.mcp_server.jsfl_bridge import (
        DEFAULT_ANIMATE_CC_EXE,
    )
    assert "Animate.exe" in DEFAULT_ANIMATE_CC_EXE


def test_render_template_no_substitutions():
    from animate_cc_pipeline.mcp_server.jsfl_bridge import _render_template
    template = "var foo = 'bar';"
    assert _render_template(template, None) == template
    assert _render_template(template, {}) == template


def test_render_template_basic_substitution():
    from animate_cc_pipeline.mcp_server.jsfl_bridge import _render_template
    template = "var path = '{{OUTPUT_PATH}}';"
    rendered = _render_template(template, {"OUTPUT_PATH": "C:/foo/bar.fla"})
    assert "C:/foo/bar.fla" in rendered
    assert "{{OUTPUT_PATH}}" not in rendered


def test_render_template_escapes_backslashes():
    """Windows paths with backslashes get doubled so they survive
    being embedded in a JSFL string literal.
    """
    from animate_cc_pipeline.mcp_server.jsfl_bridge import _render_template
    template = "{{PATH}}"
    rendered = _render_template(template, {"PATH": r"C:\foo\bar.fla"})
    assert rendered == r"C:\\foo\\bar.fla"


def test_render_template_multiple_keys():
    from animate_cc_pipeline.mcp_server.jsfl_bridge import _render_template
    template = "out={{OUT}};status={{STATUS}};"
    rendered = _render_template(
        template, {"OUT": "result.fla", "STATUS": "ok"}
    )
    assert rendered == "out=result.fla;status=ok;"


def test_render_template_non_string_value():
    """Non-string substitution values get ``str()``-converted."""
    from animate_cc_pipeline.mcp_server.jsfl_bridge import _render_template
    template = "width={{W}};height={{H}};fps={{FPS}};"
    rendered = _render_template(
        template, {"W": 1920, "H": 1080, "FPS": 25}
    )
    assert rendered == "width=1920;height=1080;fps=25;"


def test_render_template_unknown_keys_left_alone():
    """Placeholders without a matching key stay as ``{{KEY}}``."""
    from animate_cc_pipeline.mcp_server.jsfl_bridge import _render_template
    template = "{{A}}-{{B}}-{{C}}"
    rendered = _render_template(template, {"A": "x", "C": "z"})
    assert rendered == "x-{{B}}-z"


def test_resolve_animate_exe_missing_path_raises(monkeypatch, tmp_path):
    from animate_cc_pipeline.mcp_server.jsfl_bridge import _resolve_animate_exe

    fake = tmp_path / "does_not_exist" / "Animate.exe"
    monkeypatch.setenv("ANIMATE_CC_EXE", str(fake))

    with pytest.raises(FileNotFoundError, match="Animate.exe not found"):
        _resolve_animate_exe()


def test_resolve_animate_exe_env_var_wins(monkeypatch, tmp_path):
    """``ANIMATE_CC_EXE`` env var overrides the default path."""
    from animate_cc_pipeline.mcp_server.jsfl_bridge import _resolve_animate_exe

    # Create a fake "Animate.exe" file the resolver will accept.
    fake_exe = tmp_path / "FakeAnimate.exe"
    fake_exe.write_text("not really animate, but exists")
    monkeypatch.setenv("ANIMATE_CC_EXE", str(fake_exe))

    resolved = _resolve_animate_exe()
    assert resolved == fake_exe


def test_run_jsfl_template_missing_template_raises(tmp_path):
    from animate_cc_pipeline.mcp_server.jsfl_bridge import run_jsfl_template

    with pytest.raises(FileNotFoundError, match="JSFL template not found"):
        run_jsfl_template(tmp_path / "no_such.jsfl")


# ─── Integration test (actually spawns Animate.exe) ─────────────────


@pytest.mark.skipif(
    os.environ.get("SKIP_ANIMATE_TESTS") == "1",
    reason="SKIP_ANIMATE_TESTS=1 set in env",
)
def test_hello_world_creates_fla(tmp_path):
    """End-to-end: render hello_world.jsfl, run via Animate, verify
    output ``.fla`` exists.

    Auto-skips if Animate.exe is not installed on this machine. Run
    manually on a Windows box with Animate CC installed.
    """
    from animate_cc_pipeline.mcp_server.jsfl_bridge import (
        run_jsfl_template,
        _resolve_animate_exe,
    )

    try:
        _resolve_animate_exe()
    except FileNotFoundError:
        pytest.skip("Animate.exe not found on this machine")

    template_path = (
        Path(__file__).resolve().parent.parent
        / "mcp_server"
        / "jsfl_templates"
        / "hello_world.jsfl"
    )
    assert template_path.exists(), f"missing template: {template_path}"

    output_fla = tmp_path / "phase3b_smoke.fla"
    # JSFL FLfile.platformPathToURI accepts forward-slash Windows paths.
    output_path_for_jsfl = str(output_fla).replace("\\", "/")

    result = run_jsfl_template(
        template_path,
        substitutions={"OUTPUT_PATH": output_path_for_jsfl},
        timeout=120,  # Animate boot can take 10-30s on first launch
    )

    # Animate.exe sometimes exits with non-zero even on success; the
    # real signal is whether the .fla landed.
    assert output_fla.exists(), (
        f"Expected .fla at {output_fla} but it does not exist.\n"
        f"exit_code: {result.exit_code}\n"
        f"stdout: {result.stdout!r}\n"
        f"stderr: {result.stderr!r}\n"
        f"jsfl_path: {result.jsfl_path}\n"
    )
    assert output_fla.stat().st_size > 0, "produced .fla is empty"
