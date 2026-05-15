"""JSFL bridge: spawn Adobe Animate CC to execute parameterized JSFL
scripts.

Phase 3b: minimal bridge with ``run_jsfl_template()`` plus one ready
template (``hello_world.jsfl``). Future phases extend with helpers
for reading JSON results back, multi-document handling, and
long-lived Animate-instance reuse.

JSFL invocation pattern:

    Animate.exe -AlwaysRunJSFL <path-to-.jsfl-script>

Animate launches, runs the script, and (depending on what the
script does) either exits or stays open. For pure file-writing
scripts (like ``hello_world.jsfl``) it exits with code 0 on success.

Path conventions in JSFL: Animate uses URI-style paths
(``file:///C:/...``) for ``saveDocument``-style functions. We rely
on ``FLfile.platformPathToURI`` inside the JSFL script to convert
Windows backslash paths the operator passes in.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("animate_cc_mcp.jsfl_bridge")


# ─── Defaults ───────────────────────────────────────────────────────

DEFAULT_ANIMATE_CC_EXE = (
    r"C:\Program Files\Adobe\Adobe Animate 2020\Animate.exe"
)


@dataclass
class JsflResult:
    """Result of running a JSFL script via Animate.exe.

    Animate's stdout / stderr is typically empty (the app logs to its
    own Output Panel, not the parent process). The presence of
    expected output files is the real signal of success.
    """

    exit_code: int
    stdout: str
    stderr: str
    jsfl_path: str
    rendered_script: str  # the actual JSFL we ran (post-substitution)


# ─── Internals ──────────────────────────────────────────────────────

def _resolve_animate_exe() -> Path:
    """Locate Animate.exe via ``ANIMATE_CC_EXE`` env var or default path.

    Raises ``FileNotFoundError`` with a hint listing common install
    paths if neither is present on the machine.
    """
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

    JSFL string literals use backslash escaping, so any backslash in
    a substituted Windows path must be doubled to survive being
    embedded in a JSFL ``"..."`` literal. Callers can avoid this by
    using forward slashes (JSFL accepts both for ``FLfile`` paths).
    """
    if substitutions is None:
        return template_content
    rendered = template_content
    for key, value in substitutions.items():
        placeholder = "{{" + key + "}}"
        if isinstance(value, str):
            # Escape backslashes so the substituted string is valid
            # inside a JSFL string literal (``"..."``).
            escaped = value.replace("\\", "\\\\")
        else:
            escaped = str(value)
        rendered = rendered.replace(placeholder, escaped)
    return rendered


# ─── Public API ─────────────────────────────────────────────────────

def run_jsfl_template(
    template_path: Path | str,
    substitutions: dict | None = None,
    timeout: int = 60,
    keep_temp_file: bool = False,
) -> JsflResult:
    """Render a JSFL template with substitutions, then execute it via
    Animate.exe.

    Args:
        template_path: Path to a ``.jsfl`` file that may contain
            ``{{KEY}}`` placeholders.
        substitutions: Mapping of placeholder keys to replacement
            values. Strings have backslashes escaped automatically
            for JSFL literal safety.
        timeout: Subprocess timeout in seconds. JSFL scripts that
            wait for user input will hang and trip this.
        keep_temp_file: If True, do not delete the rendered ``.jsfl``
            after run — useful for debugging. The path is in the
            returned ``JsflResult``.

    Returns:
        ``JsflResult`` with exit code, captured streams, and the path
        to the executed (rendered) script.

    Raises:
        FileNotFoundError: Animate.exe or the template is missing.
        subprocess.TimeoutExpired: The script took longer than
            ``timeout`` seconds.
    """
    template_path = Path(template_path)
    if not template_path.exists():
        raise FileNotFoundError(f"JSFL template not found: {template_path}")

    template_content = template_path.read_text(encoding="utf-8")
    rendered = _render_template(template_content, substitutions)

    animate_exe = _resolve_animate_exe()

    # Place the temp script in a known directory if ANIMATE_TEMP_DIR is set,
    # else use the system temp dir.
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
        "Executing JSFL: %s (template: %s, timeout=%ds)",
        rendered_path, template_path.name, timeout,
    )

    try:
        completed = subprocess.run(
            [str(animate_exe), "-AlwaysRunJSFL", str(rendered_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return JsflResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            jsfl_path=str(rendered_path),
            rendered_script=rendered,
        )
    finally:
        if not keep_temp_file:
            try:
                rendered_path.unlink()
            except OSError:
                pass  # best-effort cleanup
