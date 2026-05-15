"""End-to-end smoke for Phase 3b.

Run manually after ``pip install -r requirements.txt`` and after
running ``tools/phase3/setup_local_python.py`` (or with PATH set to
the embedded Python):

    <embedded-python> animate_cc_pipeline/tests/_smoke_phase3b.py

What this proves:
1. The server module imports and exposes the ``ping`` tool.
2. The ``ping`` tool returns a valid response.
3. The JSFL bridge can locate Animate.exe (per ``ANIMATE_CC_EXE`` or
   default path).
4. The JSFL bridge can spawn Animate.exe with ``hello_world.jsfl``
   and produce a ``.fla`` on disk.

Exits with status 0 on success, non-zero with a diagnostic on failure.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path


def _print(line: str) -> None:
    print(line, flush=True)


def _step(name: str, ok: bool, detail: str = "") -> None:
    icon = "OK  " if ok else "FAIL"
    _print(f"  [{icon}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    _print("=" * 60)
    _print("Phase 3b smoke test")
    _print("=" * 60)

    # 1. Imports
    try:
        from animate_cc_pipeline.mcp_server import server as srv  # noqa: F401
        from animate_cc_pipeline.mcp_server import jsfl_bridge
    except Exception as exc:  # pragma: no cover
        _step("imports", False, str(exc))
        return 1
    _step("imports", True)

    # 2. List tools
    from animate_cc_pipeline.mcp_server.server import handle_list_tools
    tools = asyncio.run(handle_list_tools())
    ping_present = any(t.name == "ping" for t in tools)
    _step("ping in tool list", ping_present, f"{len(tools)} tool(s) total")
    if not ping_present:
        return 2

    # 3. Call ping
    from animate_cc_pipeline.mcp_server.server import handle_call_tool
    ping_result = asyncio.run(handle_call_tool("ping", {}))
    try:
        payload = json.loads(ping_result[0].text)
        assert payload["status"] == "ok"
    except Exception as exc:
        _step("ping responds with status=ok", False, str(exc))
        return 3
    _step(
        "ping responds with status=ok",
        True,
        f"server_version={payload['server_version']}",
    )

    # 4. Resolve Animate.exe
    try:
        animate_exe = jsfl_bridge._resolve_animate_exe()
    except FileNotFoundError as exc:
        _step("resolve Animate.exe", False, str(exc).splitlines()[0])
        _print("")
        _print("Cannot continue without Animate.exe — Phase 3b smoke aborted.")
        _print("(Unit tests still pass without Animate; set SKIP_ANIMATE_TESTS=1)")
        return 4
    _step("resolve Animate.exe", True, str(animate_exe))

    # 5. Run hello_world.jsfl
    template_path = (
        Path(__file__).resolve().parent.parent
        / "mcp_server"
        / "jsfl_templates"
        / "hello_world.jsfl"
    )
    if not template_path.exists():
        _step("hello_world.jsfl present", False, str(template_path))
        return 5
    _step("hello_world.jsfl present", True, str(template_path))

    with tempfile.TemporaryDirectory(prefix="animate_smoke_") as tmp:
        out = Path(tmp) / "smoke.fla"
        out_for_jsfl = str(out).replace("\\", "/")

        _print(f"  ... spawning Animate.exe (may take 10-30s on first launch)")
        result = jsfl_bridge.run_jsfl_template(
            template_path,
            substitutions={"OUTPUT_PATH": out_for_jsfl},
            timeout=180,
        )

        if not out.exists():
            _step(
                "Animate created .fla",
                False,
                f"exit_code={result.exit_code}; stdout={result.stdout!r}; stderr={result.stderr!r}",
            )
            return 6
        size = out.stat().st_size
        _step("Animate created .fla", True, f"{size} bytes at {out}")

    _print("")
    _print("All Phase 3b smoke steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
