"""Unit tests for tools/phase3/validate_phase3_env.py.

The validator is a CLI but the actual checks are pure functions
returning CheckResult — easy to test in isolation by monkeypatching
the inputs each check looks at (env vars, filesystem, imports).

Run via:
    <python> -m pytest animate_cc_pipeline/tests/test_validate_phase3_env.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make tools/phase3 importable. The validator lives outside the
# animate_cc_pipeline package; we point sys.path at the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.phase3 import validate_phase3_env as validator


# ─── CheckResult schema ───────────────────────────────────────────


def test_check_result_defaults():
    r = validator.CheckResult(name="x", ok=True, message="msg")
    assert r.fatal is True
    assert r.hint == ""


def test_check_result_warning_path():
    r = validator.CheckResult(name="x", ok=False, message="msg", fatal=False)
    assert r.fatal is False


# ─── Individual checks ────────────────────────────────────────────


def test_check_python_version_passes_on_311_plus():
    """We run this test on the embedded Python (3.13) so it should pass."""
    r = validator.check_python_version()
    assert r.ok is True
    assert "Python" in r.message


def test_check_required_modules_passes_on_current_env():
    """All listed modules ARE installed in the test environment."""
    r = validator.check_required_modules()
    assert r.ok is True


def test_check_required_modules_fails_on_missing(monkeypatch):
    """If a required module is missing, fails fatally with a hint."""
    real_import = validator.importlib.import_module

    def fake_import(name):
        if name == "mcp":
            raise ImportError("mocked missing")
        return real_import(name)

    monkeypatch.setattr(validator.importlib, "import_module", fake_import)
    r = validator.check_required_modules()
    assert r.ok is False
    assert "mcp" in r.message
    assert r.fatal is True
    assert "pip install" in r.hint


def test_check_optional_modules_is_never_fatal(monkeypatch):
    """Even if every optional module is missing, the check is not fatal."""
    real_import = validator.importlib.import_module

    def fake_import(name):
        if name in validator.OPTIONAL_MODULES:
            raise ImportError("not installed")
        return real_import(name)

    monkeypatch.setattr(validator.importlib, "import_module", fake_import)
    r = validator.check_optional_modules()
    assert r.ok is False
    assert r.fatal is False


def test_check_animate_exe_with_env_var(monkeypatch, tmp_path):
    """ANIMATE_CC_EXE env var pointing at an existing file → OK."""
    fake_animate = tmp_path / "Animate.exe"
    fake_animate.write_bytes(b"\x00")
    monkeypatch.setenv("ANIMATE_CC_EXE", str(fake_animate))

    r = validator.check_animate_exe()
    assert r.ok is True
    assert str(fake_animate) in r.message


def test_check_animate_exe_missing_is_not_fatal(monkeypatch, tmp_path):
    """Missing Animate.exe is a warning, not a fatal failure."""
    monkeypatch.setenv("ANIMATE_CC_EXE", str(tmp_path / "no_such_animate.exe"))
    r = validator.check_animate_exe()
    assert r.ok is False
    assert r.fatal is False
    assert "not found" in r.message


def test_check_settings_local_json_present_and_valid(monkeypatch, tmp_path):
    """A valid settings.local.json pointing at an existing Python → OK."""
    fake_python = tmp_path / "python.exe"
    fake_python.write_bytes(b"")
    settings_file = tmp_path / ".claude" / "settings.local.json"
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text(json.dumps({
        "mcpServers": {"animate-cc": {"command": str(fake_python)}}
    }), encoding="utf-8")

    monkeypatch.setattr(validator, "REPO_ROOT", tmp_path)
    r = validator.check_settings_local_json()
    assert r.ok is True


def test_check_settings_local_json_missing_is_warning(monkeypatch, tmp_path):
    """Missing settings.local.json is a warning, not fatal."""
    monkeypatch.setattr(validator, "REPO_ROOT", tmp_path)
    r = validator.check_settings_local_json()
    assert r.ok is False
    assert r.fatal is False


def test_check_settings_local_json_with_bad_command(monkeypatch, tmp_path):
    """settings.local.json with a non-existent command path → fatal failure."""
    settings_file = tmp_path / ".claude" / "settings.local.json"
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text(json.dumps({
        "mcpServers": {"animate-cc": {"command": str(tmp_path / "nope.exe")}}
    }), encoding="utf-8")

    monkeypatch.setattr(validator, "REPO_ROOT", tmp_path)
    r = validator.check_settings_local_json()
    assert r.ok is False
    assert r.fatal is True


def test_check_settings_local_json_with_invalid_json(monkeypatch, tmp_path):
    """settings.local.json that is not valid JSON → fatal failure."""
    settings_file = tmp_path / ".claude" / "settings.local.json"
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text("not valid json {", encoding="utf-8")

    monkeypatch.setattr(validator, "REPO_ROOT", tmp_path)
    r = validator.check_settings_local_json()
    assert r.ok is False
    assert "not valid JSON" in r.message


def test_check_canonical_files_exist_all_present(monkeypatch, tmp_path):
    """All six canonical files present → OK."""
    for name in validator.CANONICAL_FILES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(validator, "REPO_ROOT", tmp_path)
    r = validator.check_canonical_files_exist()
    assert r.ok is True


def test_check_canonical_files_exist_one_missing(monkeypatch, tmp_path):
    """One missing canonical file → fatal failure listing it."""
    # Create all but the first
    for name in validator.CANONICAL_FILES[1:]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(validator, "REPO_ROOT", tmp_path)
    r = validator.check_canonical_files_exist()
    assert r.ok is False
    assert validator.CANONICAL_FILES[0] in r.message


def test_check_run_wrappers_exist_passes_on_real_repo():
    """Real repo has both run wrappers."""
    r = validator.check_run_wrappers_exist()
    assert r.ok is True


def test_check_run_wrappers_missing(monkeypatch, tmp_path):
    """Missing wrappers reported as fatal."""
    monkeypatch.setattr(validator, "REPO_ROOT", tmp_path)
    r = validator.check_run_wrappers_exist()
    assert r.ok is False
    assert "run_batch.py" in r.message


def test_check_jsfl_templates_present_passes_on_real_repo():
    r = validator.check_jsfl_templates_present()
    assert r.ok is True


def test_check_jsfl_templates_missing(monkeypatch, tmp_path):
    """If templates dir is empty, fail fatally."""
    monkeypatch.setattr(validator, "REPO_ROOT", tmp_path)
    r = validator.check_jsfl_templates_present()
    assert r.ok is False
    assert "import_character_rig.jsfl" in r.message


def test_check_mcp_server_imports_passes_on_real_repo():
    r = validator.check_mcp_server_imports()
    assert r.ok is True


def test_check_pipeline_modules_import_passes_on_real_repo():
    r = validator.check_pipeline_modules_import()
    assert r.ok is True


# ─── run_all_checks aggregation ───────────────────────────────────


def test_run_all_checks_returns_one_result_per_check():
    results = validator.run_all_checks()
    assert len(results) == len(validator.ALL_CHECKS)
    for r in results:
        assert isinstance(r, validator.CheckResult)


def test_run_all_checks_catches_check_exceptions(monkeypatch):
    """If a check function itself raises, run_all_checks captures
    it as a failed CheckResult rather than aborting."""
    def crasher():
        raise RuntimeError("boom")

    monkeypatch.setattr(validator, "ALL_CHECKS", [crasher])
    results = validator.run_all_checks()
    assert len(results) == 1
    assert results[0].ok is False
    assert "crasher" in results[0].name or "<unknown>" in results[0].name
    assert "boom" in results[0].message


# ─── format_results ──────────────────────────────────────────────


def test_format_results_includes_ok_and_fail():
    results = [
        validator.CheckResult(name="a", ok=True, message="all good"),
        validator.CheckResult(name="b", ok=False, message="oh no", hint="try X"),
        validator.CheckResult(name="c", ok=False, message="warn", fatal=False, hint="optional"),
    ]
    out = validator.format_results(results)
    assert "[OK  ] a" in out
    assert "[FAIL] b" in out
    assert "[WARN] c" in out
    assert "1 ok" in out
    assert "1 warning(s)" in out
    assert "1 fatal failure(s)" in out


def test_format_results_quiet_omits_hints():
    results = [
        validator.CheckResult(name="b", ok=False, message="oh no", hint="try X"),
    ]
    out_loud = validator.format_results(results, quiet=False)
    out_quiet = validator.format_results(results, quiet=True)
    assert "try X" in out_loud
    assert "try X" not in out_quiet


# ─── CLI ─────────────────────────────────────────────────────────


def test_cli_exits_zero_when_all_ok(monkeypatch, capsys):
    """With no failures the CLI exits 0."""
    fake = [validator.CheckResult(name="x", ok=True, message="all good")]
    monkeypatch.setattr(validator, "run_all_checks", lambda: fake)
    rc = validator.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[OK  ]" in out


def test_cli_exits_one_on_fatal_failure(monkeypatch):
    fake = [validator.CheckResult(name="x", ok=False, message="fail", fatal=True)]
    monkeypatch.setattr(validator, "run_all_checks", lambda: fake)
    rc = validator.main([])
    assert rc == 1


def test_cli_exits_zero_on_warning_only(monkeypatch):
    """A non-fatal failure (warning) should still exit 0."""
    fake = [validator.CheckResult(name="x", ok=False, message="warn", fatal=False)]
    monkeypatch.setattr(validator, "run_all_checks", lambda: fake)
    rc = validator.main([])
    assert rc == 0


def test_cli_strict_promotes_warning_to_fatal(monkeypatch):
    """--strict makes warnings cause exit 1."""
    fake = [validator.CheckResult(name="x", ok=False, message="warn", fatal=False)]
    monkeypatch.setattr(validator, "run_all_checks", lambda: fake)
    rc = validator.main(["--strict"])
    assert rc == 1


def test_cli_json_output(monkeypatch, capsys):
    fake = [
        validator.CheckResult(name="a", ok=True, message="ok"),
        validator.CheckResult(name="b", ok=False, message="fail"),
    ]
    monkeypatch.setattr(validator, "run_all_checks", lambda: fake)
    rc = validator.main(["--json"])
    assert rc == 1
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["num_ok"] == 1
    assert payload["num_fatal"] == 1
    assert len(payload["results"]) == 2


def test_cli_runs_against_real_environment():
    """Smoke: the CLI actually completes without crashing on this
    machine's real config. Doesn't assert anything about the result
    — just that it exits cleanly."""
    rc = validator.main([])
    assert rc in (0, 1)  # depends on the operator's env
