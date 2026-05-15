"""JSFL bridge: spawn Adobe Animate CC to execute parameterized JSFL
scripts.

Phase 3b: parameterized template runner plus the "sentinel + force-kill"
pattern. Adobe Animate's command-line JSFL support runs the script
fine but `fl.quit()` does not reliably exit the application
(Welcome screens, "Save changes?" dialogs, and other modals keep it
alive). So instead of waiting for Animate.exe to exit, the bridge:

  1. Launches Animate.exe non-blocking (subprocess.Popen)
  2. Polls for a known output file (and optionally a sentinel) to
     appear on disk
  3. Force-kills Animate.exe once outputs are present
  4. Cleans up temp scripts

This makes Animate behave like a deterministic black-box renderer.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("animate_cc_mcp.jsfl_bridge")


# ─── Defaults ───────────────────────────────────────────────────────

DEFAULT_ANIMATE_CC_EXE = (
    r"C:\Program Files\Adobe\Adobe Animate 2020\Animate.exe"
)


@dataclass
class JsflResult:
    """Result of running a JSFL script via Animate.exe.

    The interesting fields:
      - ``completed_normally``: True if all ``expected_outputs`` exist.
      - ``exit_code``: Animate.exe's exit code if it terminated by
        itself, else None (we force-killed it).
      - ``elapsed_seconds``: time from launch to termination.
      - ``rendered_script``: the post-substitution JSFL we ran (handy
        for debugging).
      - ``jsfl_path``: filesystem path to the rendered .jsfl (kept
        only when ``keep_temp_file=True``, else deleted before return).
    """

    completed_normally: bool
    exit_code: int | None
    elapsed_seconds: float
    rendered_script: str
    jsfl_path: str
    missing_outputs: list[Path] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""


# ─── Internals ──────────────────────────────────────────────────────


def _resolve_animate_exe() -> Path:
    """Locate Animate.exe via ``ANIMATE_CC_EXE`` env var or default path."""
    raw = os.environ.get("ANIMATE_CC_EXE", DEFAULT_ANIMATE_CC_EXE)
    path = Path(raw)
    if not path.exists():
        raise FileNotFoundError(
            f"Animate.exe not found at: {path}\n\n"
            "Either:\n"
            "  1. Install Adobe Animate CC, or\n"
            "  2. Set ANIMATE_CC_EXE env var to the correct path.\n\n"
            "Common install paths to try:\n"
            "  C:\\Program Files\\Adobe\\Adobe Animate 2020\\Animate.exe\n"
            "  C:\\Program Files\\Adobe\\Adobe Animate 2022\\Animate.exe\n"
            "  C:\\Program Files\\Adobe\\Adobe Animate 2024\\Animate.exe\n"
            "  C:\\Program Files\\Adobe\\Adobe Animate 2025\\Animate.exe\n"
        )
    return path


def _render_template(template_content: str, substitutions: dict | None) -> str:
    """Substitute ``{{KEY}}`` placeholders with values.

    Backslashes in string values are doubled so they survive being
    embedded in a JSFL ``"..."`` literal.
    """
    if substitutions is None:
        return template_content
    rendered = template_content
    for key, value in substitutions.items():
        placeholder = "{{" + key + "}}"
        if isinstance(value, str):
            escaped = value.replace("\\", "\\\\")
        else:
            escaped = str(value)
        rendered = rendered.replace(placeholder, escaped)
    return rendered


def _kill_animate(timeout_s: float = 10.0) -> None:
    """Force-kill any running Animate.exe processes.

    Used after sentinel detection (Animate refuses to exit on its
    own) and at bridge startup (a stale instance would otherwise
    delegate our new JSFL invocation to itself).
    """
    # /F = force, /T = kill child tree, /IM = by image name
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/IM", "Animate.exe"],
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("taskkill Animate.exe failed: %s", exc)

    # Brief sleep so Windows finishes releasing the process handle
    time.sleep(0.5)


def _animate_running() -> bool:
    """Return True if any Animate.exe process is currently running."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Animate.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return "Animate.exe" in out.stdout
    except Exception:
        return False


# ─── Public API ─────────────────────────────────────────────────────


def run_jsfl_template(
    template_path: Path | str,
    substitutions: dict | None = None,
    expected_outputs: Iterable[Path | str] | None = None,
    poll_interval: float = 0.5,
    poll_timeout: float = 180.0,
    boot_grace: float = 5.0,
    keep_temp_file: bool = False,
    kill_existing_first: bool = True,
) -> JsflResult:
    """Render a JSFL template and execute it via Animate.exe, using
    sentinel-polling + force-kill for reliable termination.

    Args:
        template_path: Path to a .jsfl template with ``{{KEY}}``
            placeholders.
        substitutions: Mapping of placeholder keys to replacement
            values. Strings have their backslashes escaped to remain
            valid inside JSFL string literals.
        expected_outputs: One or more files the JSFL is expected to
            create. Polling continues until ALL of them exist or
            poll_timeout is reached. Pass a sentinel file path here
            (in addition to the real output) for explicit
            "JSFL done" signaling. If None, the bridge falls back to
            ``subprocess.run`` and waits for Animate to exit on its
            own (often unreliable; prefer expected_outputs).
        poll_interval: Seconds between filesystem checks.
        poll_timeout: Maximum seconds to wait for all expected_outputs
            to appear before giving up + force-killing Animate.
        boot_grace: Minimum seconds to wait after launching Animate
            before polling. Avoids force-killing during boot.
        keep_temp_file: If True, do not delete the rendered .jsfl
            after run. Useful for debugging.
        kill_existing_first: If True, taskkill any running Animate.exe
            before launching. Avoids the "new instance delegates to
            existing + exits immediately" failure mode.

    Returns:
        ``JsflResult`` with success flag, exit code (if Animate quit
        on its own), elapsed time, and which expected_outputs were
        missing (if any).

    Raises:
        FileNotFoundError: Animate.exe or template path missing.
    """
    template_path = Path(template_path)
    if not template_path.exists():
        raise FileNotFoundError(f"JSFL template not found: {template_path}")

    expected: list[Path] = [Path(p) for p in (expected_outputs or [])]

    template_content = template_path.read_text(encoding="utf-8")
    rendered = _render_template(template_content, substitutions)

    animate_exe = _resolve_animate_exe()

    if kill_existing_first and _animate_running():
        logger.info("Killing existing Animate.exe instance(s) before launch")
        _kill_animate()

    # Render JSFL to temp file
    temp_dir_raw = os.environ.get("ANIMATE_TEMP_DIR", "").strip()
    temp_dir = Path(temp_dir_raw) if temp_dir_raw else Path(tempfile.gettempdir())
    temp_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".jsfl",
        prefix="animate_mcp_",
        dir=str(temp_dir),
        delete=False,
        encoding="utf-8",
    ) as fh:
        fh.write(rendered)
        rendered_path = Path(fh.name)

    logger.info(
        "Launching Animate.exe with JSFL: %s (template: %s)",
        rendered_path, template_path.name,
    )

    start = time.monotonic()

    # ─── Fall-through path: no expected_outputs → old behavior ─────
    if not expected:
        try:
            completed = subprocess.run(
                [str(animate_exe), "-AlwaysRunJSFL", str(rendered_path)],
                capture_output=True,
                text=True,
                timeout=poll_timeout,
                check=False,
            )
            elapsed = time.monotonic() - start
            return JsflResult(
                completed_normally=(completed.returncode == 0),
                exit_code=completed.returncode,
                elapsed_seconds=elapsed,
                rendered_script=rendered,
                jsfl_path=str(rendered_path),
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        finally:
            if not keep_temp_file:
                _safe_unlink(rendered_path)

    # ─── Sentinel-polling path (preferred) ────────────────────────
    proc = subprocess.Popen(
        [str(animate_exe), "-AlwaysRunJSFL", str(rendered_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        # Give Animate time to boot. Polling earlier would just
        # waste CPU.
        time.sleep(boot_grace)

        deadline = start + poll_timeout
        while time.monotonic() < deadline:
            missing = [p for p in expected if not p.exists()]
            if not missing:
                # All expected outputs present — JSFL is done.
                # Force-kill Animate (it won't exit on its own).
                logger.info(
                    "All expected_outputs present (%.1fs elapsed); killing Animate.exe",
                    time.monotonic() - start,
                )
                _kill_animate()
                elapsed = time.monotonic() - start
                return JsflResult(
                    completed_normally=True,
                    exit_code=None,
                    elapsed_seconds=elapsed,
                    rendered_script=rendered,
                    jsfl_path=str(rendered_path),
                )
            # Has Animate exited on its own? Rare but possible
            if proc.poll() is not None:
                # Animate quit. Check outputs again immediately.
                missing = [p for p in expected if not p.exists()]
                elapsed = time.monotonic() - start
                return JsflResult(
                    completed_normally=not missing,
                    exit_code=proc.returncode,
                    elapsed_seconds=elapsed,
                    rendered_script=rendered,
                    jsfl_path=str(rendered_path),
                    missing_outputs=missing,
                )
            time.sleep(poll_interval)

        # Timed out waiting for outputs
        logger.warning(
            "poll_timeout (%.0fs) elapsed; expected_outputs still missing: %s",
            poll_timeout, [str(p) for p in expected if not p.exists()],
        )
        _kill_animate()
        elapsed = time.monotonic() - start
        return JsflResult(
            completed_normally=False,
            exit_code=None,
            elapsed_seconds=elapsed,
            rendered_script=rendered,
            jsfl_path=str(rendered_path),
            missing_outputs=[p for p in expected if not p.exists()],
        )
    finally:
        # Make sure Animate is dead in any exit path
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
        if not keep_temp_file:
            _safe_unlink(rendered_path)


def _safe_unlink(p: Path) -> None:
    try:
        p.unlink()
    except OSError:
        pass
