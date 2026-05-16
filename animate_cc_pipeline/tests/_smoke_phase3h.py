"""End-to-end smoke for Phase 3h audio + lipsync tools.

Run manually:
    <python> animate_cc_pipeline/tests/_smoke_phase3h.py

What this proves:
1. import_audio embeds a small WAV into the .fla on an AUDIO layer.
2. _setup_phase3h_test_fla.jsfl builds a Graphic Symbol with 3
   named keyframes (mouth_A, mouth_E, mouth_O).
3. set_switch_state("MOUTH", 1, "mouth_E") pins the MouthSwitch
   instance to its mouth_E frame (firstFrame should become 1
   since mouth_E is the second labeled keyframe).
4. get_graphic_first_frame (Phase 3f) verifies firstFrame=1.
5. apply_auto_lipsync attempted — non-fatal on error (experimental).

The WAV is generated via Python's stdlib `wave` module (0.5s
silence at 44.1kHz mono, ~22 KB).

Wall time ~130-180s (7-8 Animate launches).
"""

from __future__ import annotations

import asyncio
import json
import struct
import sys
import tempfile
import wave
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _print(line: str) -> None:
    print(line, flush=True)


def _step(name: str, ok: bool, detail: str = "") -> None:
    icon = "OK  " if ok else "FAIL"
    _print(f"  [{icon}] {name}" + (f" - {detail}" if detail else ""))


def _make_silent_wav(path: Path, duration_s: float = 0.5, rate: int = 44100) -> None:
    """Write a tiny silent WAV via stdlib `wave`."""
    frame_count = int(duration_s * rate)
    silent_frame = struct.pack("<h", 0)  # 16-bit signed PCM, value 0
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)        # mono
        w.setsampwidth(2)        # 16-bit
        w.setframerate(rate)
        w.writeframes(silent_frame * frame_count)


def main() -> int:
    _print("=" * 60)
    _print("Phase 3h smoke test")
    _print("=" * 60)

    try:
        from animate_cc_pipeline.mcp_server.tools import document as doc_tools
        from animate_cc_pipeline.mcp_server.tools import audio as audio_tools
        from animate_cc_pipeline.mcp_server.tools import bone as bone_tools
        from animate_cc_pipeline.mcp_server import jsfl_bridge
    except Exception as exc:
        _step("imports", False, str(exc))
        return 1
    _step("imports", True)

    try:
        animate_exe = jsfl_bridge._resolve_animate_exe()
    except FileNotFoundError as exc:
        _step("resolve Animate.exe", False, str(exc).splitlines()[0])
        return 2
    _step("resolve Animate.exe", True, str(animate_exe))

    with tempfile.TemporaryDirectory(prefix="animate_smoke3h_") as tmp:
        tmp_dir = Path(tmp)
        fla = tmp_dir / "phase3h.fla"
        wav = tmp_dir / "silence.wav"
        setup_sentinel = tmp_dir / "setup.sentinel"

        # 1. create_document
        _print("  ... create_document (Animate launch)")
        r = asyncio.run(doc_tools.handle_create_document({
            "fla_path": str(fla), "width": 1920, "height": 1080, "fps": 25,
        }))
        if json.loads(r[0].text).get("status") != "ok":
            _step("create_document", False, r[0].text); return 3
        empty_size = fla.stat().st_size
        _step("create_document", True, f"{empty_size} bytes")

        # 2. Generate a small silent WAV
        try:
            _make_silent_wav(wav, duration_s=0.5)
        except Exception as exc:
            _step("generate silent WAV", False, str(exc))
            return 4
        _step("generate silent WAV", True, f"{wav.stat().st_size} bytes")

        # 3. import_audio
        _print("  ... import_audio onto AUDIO layer (Animate launch)")
        r = asyncio.run(audio_tools.handle_import_audio({
            "fla_path": str(fla),
            "audio_path": str(wav),
            "layer_name": "AUDIO",
            "frame": 1,
        }))
        payload = json.loads(r[0].text)
        if payload.get("status") != "ok":
            _step("import_audio", False, json.dumps(payload)); return 5
        after_audio_size = fla.stat().st_size
        if after_audio_size <= empty_size:
            _step("import_audio grew .fla", False,
                  f"size unchanged: {after_audio_size} vs {empty_size}")
            return 6
        _step("import_audio",
              True,
              f"{empty_size} -> {after_audio_size} bytes ({payload['elapsed_seconds']}s)")

        # 4. Build a MouthSwitch Graphic with labeled frames + place instance
        _print("  ... build MouthSwitch Graphic + place instance (Animate launch)")
        setup_template = (
            _REPO_ROOT / "animate_cc_pipeline" / "mcp_server"
            / "jsfl_templates" / "_setup_phase3h_test_fla.jsfl"
        )
        setup_result = jsfl_bridge.run_jsfl_template(
            setup_template,
            substitutions={
                "FLA_PATH": str(fla).replace("\\", "/"),
                "SENTINEL_PATH": str(setup_sentinel).replace("\\", "/"),
            },
            expected_outputs=[setup_sentinel],
            poll_timeout=240.0,
        )
        if not setup_result.completed_normally:
            _step("setup MouthSwitch", False,
                  f"missing={setup_result.missing_outputs}"); return 7
        _step("setup MouthSwitch", True, f"{setup_result.elapsed_seconds:.1f}s")

        # 5. set_switch_state to "mouth_E"
        _print("  ... set_switch_state MOUTH frame 1 -> mouth_E (Animate launch)")
        r = asyncio.run(audio_tools.handle_set_switch_state({
            "fla_path": str(fla),
            "layer_name": "MOUTH",
            "frame": 1,
            "state_name": "mouth_E",
        }))
        payload = json.loads(r[0].text)
        if payload.get("status") != "ok":
            _step("set_switch_state", False, json.dumps(payload)); return 8
        _step("set_switch_state", True, f"{payload['elapsed_seconds']}s")

        # 6. Verify via get_graphic_first_frame — expect firstFrame=1
        _print("  ... verify firstFrame == 1 via get_graphic_first_frame (Animate launch)")
        r = asyncio.run(bone_tools.handle_get_graphic_first_frame({
            "fla_path": str(fla), "layer_name": "MOUTH", "frame": 1,
        }))
        payload = json.loads(r[0].text)
        if payload.get("status") != "ok" or not payload.get("found"):
            _step("verify firstFrame", False, json.dumps(payload)); return 9
        ff = payload.get("firstFrame")
        loop = payload.get("loop")
        ff_ok = (ff == 1)
        loop_ok = (loop == "single frame")
        _step("readback.firstFrame == 1", ff_ok, f"got {ff}")
        _step("readback.loop == 'single frame'", loop_ok, f"got {loop!r}")
        if not (ff_ok and loop_ok):
            return 10

        # 7. apply_auto_lipsync — experimental, non-fatal
        _print("  ... apply_auto_lipsync (experimental, Animate launch)")
        r = asyncio.run(audio_tools.handle_apply_auto_lipsync({
            "fla_path": str(fla),
            "audio_layer": "AUDIO",
            "mouth_layer": "MOUTH",
        }))
        payload = json.loads(r[0].text)
        if payload.get("status") == "ok":
            _step("apply_auto_lipsync (experimental)", True, f"{payload['elapsed_seconds']}s")
        else:
            _step(
                "apply_auto_lipsync (experimental, non-fatal)",
                True,
                f"experimental — did not pass cleanly: {payload.get('error', '?')}",
            )

    _print("")
    _print("All Phase 3h smoke steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
