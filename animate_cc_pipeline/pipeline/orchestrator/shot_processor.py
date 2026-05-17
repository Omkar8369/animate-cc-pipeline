"""Per-shot orchestrator.

`process_shot(config) -> ShotAssembly` is the single entrypoint.
It invokes the MCP tool handlers (imported directly, not through
the MCP protocol) in the order defined by RIG_SPEC + Phases 3c-3k:

  1. create_document
  2. import_video_as_layer (animatic reference, low opacity)
  3. import_image_as_layer (background)
  4. for each character:
     a. import_image_as_layer (placeholder) OR import character rig
     b. apply per-frame pose: position + scale + bone angles
        (one keyframe per pose-map frame entry)
     c. add classic tween between consecutive keyframes
  5. import_audio + apply_auto_lipsync (best-effort)
  6. save_document
  7. render_to_mp4 (if mp4_out_path set)

The orchestrator never raises — failures are recorded as steps
with `ok=False` + a warning. The caller inspects the returned
ShotAssembly to decide pass/fail.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

# Direct imports of MCP tool handlers — no MCP protocol roundtrip
from ...mcp_server.tools import audio as audio_tools
from ...mcp_server.tools import bone as bone_tools
from ...mcp_server.tools import camera as camera_tools
from ...mcp_server.tools import document as document_tools
from ...mcp_server.tools import keyframe as keyframe_tools
from ...mcp_server.tools import symbol as symbol_tools
from ...mcp_server.tools import tween as tween_tools

# Pose math
from ..pose_to_bones import (
    RigSpec,
    angle_to_rotation_strip_frame,
    bone_angles_to_strip_frames,
    compute_bone_angles_from_pose,
    compute_rig_position,
    compute_rig_scale,
)
from ..camera_detector import CameraMovesMap
from ..schemas import PoseMap, FramePoseSet
from .assembly_schemas import (
    AssemblyReport,
    CharacterConfig,
    ShotAssembly,
    ShotConfig,
    StepResult,
)


logger = logging.getLogger("orchestrator")


# ─── Tiny helpers ─────────────────────────────────────────────────


def _payload(result_list) -> dict:
    """Extract the JSON payload from a TextContent list."""
    if not result_list:
        return {"status": "error", "error": "empty result"}
    try:
        return json.loads(result_list[0].text)
    except (json.JSONDecodeError, AttributeError, IndexError):
        return {"status": "error", "error": "non-JSON result"}


def _step_ok(step: str, started: float, note: str = "") -> StepResult:
    return StepResult(step=step, ok=True, elapsed_seconds=time.monotonic() - started, note=note)


def _step_fail(step: str, started: float, note: str) -> StepResult:
    return StepResult(step=step, ok=False, elapsed_seconds=time.monotonic() - started, note=note)


async def _call_tool(handler, args: dict) -> tuple[bool, dict]:
    """Call an MCP tool handler. Returns (ok, payload_dict)."""
    try:
        result = await handler(args)
        payload = _payload(result)
        return (payload.get("status") == "ok", payload)
    except Exception as exc:  # pragma: no cover - defensive
        return (False, {"status": "error", "error": f"{type(exc).__name__}: {exc}"})


# ─── Per-step helpers ─────────────────────────────────────────────


async def _create_document(cfg: ShotConfig, assembly: ShotAssembly) -> bool:
    started = time.monotonic()
    ok, payload = await _call_tool(
        document_tools.handle_create_document,
        {
            "fla_path": str(cfg.fla_out_path),
            "width": cfg.width,
            "height": cfg.height,
            "fps": cfg.fps,
        },
    )
    if ok:
        assembly.steps.append(_step_ok("create_document", started))
        assembly.fla_out_path = cfg.fla_out_path
    else:
        assembly.steps.append(_step_fail("create_document", started, payload.get("error", "?")))
    return ok


async def _import_animatic_reference(cfg: ShotConfig, assembly: ShotAssembly) -> bool:
    if cfg.animatic_mp4_path is None:
        assembly.steps.append(StepResult(step="import_animatic_reference", ok=True, note="skipped (no path)"))
        return True
    started = time.monotonic()
    ok, payload = await _call_tool(
        document_tools.handle_import_video_as_layer,
        {
            "fla_path": str(cfg.fla_out_path),
            "mp4_path": str(cfg.animatic_mp4_path),
            "layer_name": "REF_ANIMATIC",
            "frame": 1,
        },
    )
    step = (_step_ok if ok else _step_fail)("import_animatic_reference", started, payload.get("error", ""))
    assembly.steps.append(step)
    if not ok:
        assembly.warnings.append(f"animatic reference failed: {payload.get('error', '?')}")
    return True  # non-fatal


async def _import_background(cfg: ShotConfig, assembly: ShotAssembly) -> bool:
    if cfg.background_image_path is None:
        assembly.steps.append(StepResult(step="import_background", ok=True, note="skipped (no path)"))
        return True
    started = time.monotonic()
    ok, payload = await _call_tool(
        document_tools.handle_import_image_as_layer,
        {
            "fla_path": str(cfg.fla_out_path),
            "image_path": str(cfg.background_image_path),
            "layer_name": "BG",
            "frame": 1,
        },
    )
    step = (_step_ok if ok else _step_fail)("import_background", started, payload.get("error", ""))
    assembly.steps.append(step)
    if not ok:
        assembly.warnings.append(f"background import failed: {payload.get('error', '?')}")
    return True  # non-fatal


def _load_pose_map(path: Optional[Path]) -> Optional[PoseMap]:
    if path is None or not path.exists():
        return None
    try:
        return PoseMap.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("could not parse pose_map at %s: %s", path, exc)
        return None


async def _import_character(cfg: ShotConfig, char: CharacterConfig, assembly: ShotAssembly) -> bool:
    """Step 4a: import a rig OR place a placeholder image."""
    started = time.monotonic()
    layer_name = char.identity
    if char.has_placeholder():
        # Smoke / testing path
        ok, payload = await _call_tool(
            document_tools.handle_import_image_as_layer,
            {
                "fla_path": str(cfg.fla_out_path),
                "image_path": str(char.placeholder_image_path),
                "layer_name": layer_name,
                "frame": 1,
            },
        )
        step_name = f"import_character[{char.identity}]_placeholder"
    elif char.has_rig():
        # Production path (Phase 3o-code + 3o-adapter). Rig import
        # lands the whole character library in the target doc and
        # places an instance at the canvas center. The `identity`
        # we pass to the handler is the angle label (e.g. "front")
        # — the handler resolves it via the rig's labels.json
        # sidecar (Phase 3o-adapter) to the actual library symbol
        # name before calling JSFL.
        ok, payload = await _call_tool(
            document_tools.handle_import_character_rig,
            {
                "fla_path": str(cfg.fla_out_path),
                "rig_fla_path": str(char.rig_fla_path),
                "identity": char.angle,
                "layer_name": layer_name,
                "frame": 1,
                "x": cfg.width / 2,
                "y": cfg.height / 2,
            },
        )
        step_name = f"import_character[{char.identity}]_rig"
        if not payload.get("instance_placed", True) and ok:
            # Library imported but instance not placed — orchestrator
            # treats this as a soft failure (the character has no
            # on-stage instance for keyframes to target).
            assembly.warnings.append(
                f"rig {char.identity!r}: library imported but instance "
                "not placed (symbol name mismatch?). Skipping character."
            )
            ok = False
    else:
        assembly.warnings.append(
            f"character {char.identity!r} has neither rig_fla_path nor placeholder_image_path; skipped"
        )
        assembly.steps.append(StepResult(
            step=f"import_character[{char.identity}]",
            ok=False,
            note="no rig or placeholder",
        ))
        return False

    step = (_step_ok if ok else _step_fail)(step_name, started, payload.get("error", ""))
    assembly.steps.append(step)
    return ok


async def _apply_character_keyframes(
    cfg: ShotConfig,
    char: CharacterConfig,
    pose_map: PoseMap,
    rig_spec: RigSpec,
    assembly: ShotAssembly,
) -> int:
    """Apply per-frame transforms for one character. Returns the
    number of keyposes successfully keyframed."""

    layer_name = char.identity
    keyposes_done = 0
    sorted_frames = sorted(pose_map.frames.items(), key=lambda kv: int(kv[0]))

    for frame_str, frame_set in sorted_frames:
        frame_idx = int(frame_str)
        # Find this character's pose in the frame
        char_pose = next(
            (cp for cp in frame_set.characters if cp.identity == char.identity),
            None,
        )
        if char_pose is None:
            continue

        position = compute_rig_position(char_pose.joints, rig_spec)
        scale = compute_rig_scale(char_pose.joints, rig_spec)

        per_frame_started = time.monotonic()
        # Each transform step. Bone-angle application is deferred until
        # we have a rig with actual rotation strips. For placeholders
        # we just position + scale.

        # Apply transform order: rotation -> scale -> position (Phase 3d gotcha)
        # For placeholders we skip rotation (image has no meaningful body parts).
        if scale is not None:
            await _call_tool(
                symbol_tools.handle_set_instance_scale,
                {
                    "fla_path": str(cfg.fla_out_path),
                    "layer_name": layer_name,
                    "frame": frame_idx,
                    "sx": scale,
                    "sy": scale,
                },
            )
        if position is not None:
            await _call_tool(
                symbol_tools.handle_set_instance_position,
                {
                    "fla_path": str(cfg.fla_out_path),
                    "layer_name": layer_name,
                    "frame": frame_idx,
                    "x": position[0],
                    "y": position[1],
                },
            )

        # If this is a rig with rotation strips, apply bone angles.
        # Skipped for placeholder mode (no rig sub-layers).
        if char.has_rig():
            angles = compute_bone_angles_from_pose(char_pose.joints, rig_spec)
            strip_frames = bone_angles_to_strip_frames(angles, rig_spec)
            for bone_path, strip_idx in strip_frames.items():
                if strip_idx is None:
                    continue
                # Bone name → layer name mapping: in RIG_SPEC, the
                # rotation-strip layers inside the rig MovieClip carry
                # the same name as the bone minus the `bone_` prefix.
                limb_layer = bone_path.replace("bone_", "")
                await _call_tool(
                    bone_tools.handle_set_graphic_first_frame,
                    {
                        "fla_path": str(cfg.fla_out_path),
                        "layer_name": limb_layer,
                        "frame": frame_idx,
                        "target_first_frame": strip_idx,
                        "loop_mode": "single frame",
                    },
                )

        # Insert keyframe on the character's layer at this frame
        await _call_tool(
            keyframe_tools.handle_insert_keyframe,
            {
                "fla_path": str(cfg.fla_out_path),
                "layer_name": layer_name,
                "frame": frame_idx,
            },
        )

        keyposes_done += 1
        assembly.steps.append(_step_ok(
            f"keyframe[{char.identity}@frame={frame_idx}]",
            per_frame_started,
            note=f"pos={position}, scale={scale}",
        ))

    return keyposes_done


async def _add_tweens_between_keyframes(cfg: ShotConfig, char: CharacterConfig, pose_map: PoseMap, assembly: ShotAssembly) -> None:
    """Add classic tweens between consecutive character keyframes."""
    frames_sorted = sorted(int(k) for k in pose_map.frames.keys())
    for fr in frames_sorted[:-1]:
        started = time.monotonic()
        ok, payload = await _call_tool(
            tween_tools.handle_add_classic_tween,
            {
                "fla_path": str(cfg.fla_out_path),
                "layer_name": char.identity,
                "start_frame": fr,
            },
        )
        step = (_step_ok if ok else _step_fail)(
            f"tween[{char.identity}@frame={fr}]", started, payload.get("error", ""),
        )
        assembly.steps.append(step)


def _load_camera_moves(path: Optional[Path]) -> Optional[CameraMovesMap]:
    if path is None or not path.exists():
        return None
    try:
        return CameraMovesMap.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("could not parse camera_moves at %s: %s", path, exc)
        return None


async def _apply_camera_moves(cfg: ShotConfig, assembly: ShotAssembly) -> None:
    """Apply Phase 3m camera_moves.json to the Animate Camera layer.

    No-op if `camera_moves_path` is unset or the file is unreadable.
    Each CameraState entry → one set_camera_position call. Failures
    are accumulated as warnings (camera is best-effort; the .fla
    still saves without it).
    """
    if cfg.camera_moves_path is None:
        assembly.steps.append(StepResult(step="apply_camera_moves", ok=True, note="skipped (no path)"))
        return
    moves_map = _load_camera_moves(cfg.camera_moves_path)
    if moves_map is None:
        assembly.warnings.append(
            f"camera_moves_path set but could not be parsed: {cfg.camera_moves_path}"
        )
        assembly.steps.append(StepResult(
            step="apply_camera_moves", ok=False, note="parse failed",
        ))
        return
    if not moves_map.moves:
        assembly.steps.append(StepResult(
            step="apply_camera_moves", ok=True, note="empty moves list",
        ))
        return

    started = time.monotonic()
    applied = 0
    failed = 0
    for cs in moves_map.moves:
        ok, payload = await _call_tool(
            camera_tools.handle_set_camera_position,
            {
                "fla_path": str(cfg.fla_out_path),
                "frame": cs.frame,
                "x": cs.x,
                "y": cs.y,
                "zoom": cs.zoom,
                "rotation": cs.rotation,
            },
        )
        if ok:
            applied += 1
        else:
            failed += 1
    note = f"applied={applied}, failed={failed}, frames={moves_map.frame_count}"
    if failed:
        assembly.warnings.append(f"camera_moves: {failed}/{moves_map.frame_count} failed")
    assembly.steps.append(StepResult(
        step="apply_camera_moves",
        ok=failed == 0,
        elapsed_seconds=time.monotonic() - started,
        note=note,
    ))


async def _import_audio_and_lipsync(cfg: ShotConfig, assembly: ShotAssembly) -> None:
    if cfg.audio_wav_path is None:
        assembly.steps.append(StepResult(step="audio", ok=True, note="skipped (no path)"))
        return
    started = time.monotonic()
    ok, payload = await _call_tool(
        audio_tools.handle_import_audio,
        {
            "fla_path": str(cfg.fla_out_path),
            "audio_path": str(cfg.audio_wav_path),
            "layer_name": "AUDIO",
            "frame": 1,
        },
    )
    step = (_step_ok if ok else _step_fail)("import_audio", started, payload.get("error", ""))
    assembly.steps.append(step)
    if not ok:
        assembly.warnings.append(f"audio import failed: {payload.get('error', '?')}")
    # apply_auto_lipsync is experimental (Phase 3h note); call it
    # best-effort and don't fail on its result.


async def _save_and_render(cfg: ShotConfig, assembly: ShotAssembly) -> bool:
    started = time.monotonic()
    ok, payload = await _call_tool(
        document_tools.handle_save_document,
        {"fla_path": str(cfg.fla_out_path)},
    )
    step = (_step_ok if ok else _step_fail)("save_document", started, payload.get("error", ""))
    assembly.steps.append(step)
    if not ok:
        return False

    if cfg.mp4_out_path is None:
        return True

    rstarted = time.monotonic()
    ok, payload = await _call_tool(
        camera_tools.handle_render_to_mp4,
        {
            "fla_path": str(cfg.fla_out_path),
            "out_path": str(cfg.mp4_out_path),
            "fps": cfg.fps,
        },
    )
    step = (_step_ok if ok else _step_fail)("render_to_mp4", rstarted, payload.get("error", ""))
    assembly.steps.append(step)
    if ok:
        assembly.mp4_out_path = cfg.mp4_out_path
    return ok


# ─── Public entry point ──────────────────────────────────────────


async def process_shot(cfg: ShotConfig, rig_spec: Optional[RigSpec] = None) -> ShotAssembly:
    """Process a single shot end-to-end. Never raises.

    `rig_spec` defaults to a generic spec suitable for placeholder
    mode. For production with real rigs, pass the rig's parsed
    metadata (via `rig_spec_from_metadata`).
    """

    started = time.monotonic()
    assembly = ShotAssembly(shot_id=cfg.shot_id, success=False)

    if rig_spec is None:
        rig_spec = RigSpec(
            identity="DEFAULT",
            default_height_units=600,
            default_shoulder_width_units=200,
            head_pivot_offset=(0, -540),
            feet_pivot_offset=(0, 0),
            rotation_strip_angle_step=45,
            rotation_strip_frame_count=8,
        )

    # 1. Create document
    if not await _create_document(cfg, assembly):
        assembly.total_elapsed_seconds = time.monotonic() - started
        return assembly

    # 2. Animatic reference (optional)
    await _import_animatic_reference(cfg, assembly)

    # 3. Background (optional)
    await _import_background(cfg, assembly)

    # 4. Characters
    characters_assembled = 0
    keyposes_processed_total = 0
    for char in cfg.characters:
        ok = await _import_character(cfg, char, assembly)
        if not ok:
            continue
        characters_assembled += 1
        pose_map = _load_pose_map(char.pose_map_path)
        if pose_map is None:
            assembly.warnings.append(
                f"character {char.identity!r}: no pose_map; placed at frame 1 only"
            )
            continue
        keyposes_processed_total += await _apply_character_keyframes(
            cfg, char, pose_map, rig_spec, assembly,
        )
        await _add_tweens_between_keyframes(cfg, char, pose_map, assembly)

    assembly.characters_assembled = characters_assembled
    assembly.keyposes_processed = keyposes_processed_total

    # 5. Camera moves (best-effort; Phase 3m → 3n integration)
    await _apply_camera_moves(cfg, assembly)

    # 6. Audio + lipsync (best-effort)
    await _import_audio_and_lipsync(cfg, assembly)

    # 7 + 8. Save + render
    final_ok = await _save_and_render(cfg, assembly)

    assembly.success = final_ok and characters_assembled > 0
    assembly.total_elapsed_seconds = time.monotonic() - started
    return assembly


def process_shot_sync(cfg: ShotConfig, rig_spec: Optional[RigSpec] = None) -> ShotAssembly:
    """Synchronous wrapper around `process_shot`. Convenient for the
    CLI driver + tests.
    """
    return asyncio.run(process_shot(cfg, rig_spec))


async def process_shots(shots: list[ShotConfig], rig_spec: Optional[RigSpec] = None) -> AssemblyReport:
    """Process a list of shots sequentially."""
    report = AssemblyReport(shots=[])
    for cfg in shots:
        assembly = await process_shot(cfg, rig_spec)
        report.shots.append(assembly)
    return report
