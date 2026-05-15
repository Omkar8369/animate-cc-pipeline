"""End-to-end smoke for Phase 3b.

Run manually after ``pip install -r requirements.txt`` and after
running ``tools/phase3/setup_local_python.py``:

    <python> animate_cc_pipeline/tests/_smoke_phase3b.py

What this proves:
1. The server module imports and exposes the ``ping`` tool.
2. The ``ping`` tool returns a valid response.
3. The JSFL bridge can locate Animate.exe (per ``ANIMATE_CC_EXE`` or
   default path).
4. The JSFL bridge can spawn Animate.exe with ``hello_world.jsfl``,
   poll for the .fla + sentinel, then force-kill Animate cleanly.

Exits with status 0 on success, non-zero with a diagnostic on failure.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

# sys.path fixup so this file works as a standalone script (not via pytest)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _print(line: str) -> None:
    print(line, flush=True)


def _step(name: str, ok: bool, detail: str = "") -> None:
    icon = "OK  " if ok else "FAIL"
    _print(f"  [{icon}] {name}" + (f" - {detail}" if detail else ""))


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
        _print("Cannot continue without Animate.exe - Phase 3b smoke aborted.")
        return 4
    _step("resolve Animate.exe", True, str(animate_exe))

    # 5. Locate hello_world.jsfl
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

    # 6. Launch Animate, poll for .fla + sentinel
    with tempfile.TemporaryDirectory(prefix="animate_smoke_") as tmp:
        out = Path(tmp) / "smoke.fla"
        sentinel = Path(tmp) / "smoke.done"

        _print("  ... launching Animate.exe (10-30s cold boot, then poll for outputs)")
        result = jsfl_bridge.run_jsfl_template(
            template_path,
            substitutions={
                "OUTPUT_PATH": str(out).replace("\\", "/"),
                "SENTINEL_PATH": str(sentinel).replace("\\", "/"),
            },
            expected_outputs=[out, sentinel],
            poll_timeout=180.0,
            boot_grace=5.0,
        )

        if not result.completed_normally:
            _step(
                "Animate created .fla + sentinel",
                False,
                f"elapsed={result.elapsed_seconds:.1f}s; "
                f"missing={[str(p.name) for p in result.missing_outputs]}",
            )
            return 6

        size = out.stat().st_size if out.exists() else 0
        _step(
            "Animate created .fla + sentinel",
            True,
            f"{size} bytes in {result.elapsed_seconds:.1f}s",
        )

    _print("")
    _print("All Phase 3b smoke steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
