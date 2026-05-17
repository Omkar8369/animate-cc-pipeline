# animate_cc_pipeline/

Main code for the Animate CC Pipeline.

## Layout

- `mcp_server/` — Python MCP server bridging Claude ↔ Animate CC.
  Each subfolder = one category of Animate operations (document,
  symbol, keyframe, bone, tween, audio, camera, render).
- `pipeline/` — pure-Python pipeline nodes (no Animate dependency):
  - `pose_estimator.py` + `pose_backends/` (3j)
  - `cli_node6_pose.py` Node 6 CLI (3j)
  - `pose_to_bones.py` joint-coordinates → bone-angles math (3k)
  - `camera_detector.py` + `cli_camera_detector.py` —
    phase-correlation camera-move detection, emits camera_moves.json (3m)
  - `batch_runner.py` + `cli_batch.py` — production batch driver with
    retry policy + JSONL progress + aggregate BatchReport (3n)
  - `orchestrator/`:
    - `assembly_schemas.py` `ShotConfig` + `ShotAssembly`
    - `shot_processor.py` per-shot driver (3l)
    - `cli_node7_animate.py` single-config orchestrator CLI (3l)
- `rig_contracts/` — `rig_validator.py` that enforces
  `docs/RIG_SPEC_v1.md`
- `tests/` — pytest suite + end-to-end smoke

## How the pieces fit

```
   Claude Code (operator + Claude conversation)
        │
        │  MCP protocol
        ▼
   mcp_server/server.py  ← stateless tool router
        │
        ├──► tools/document.py   ──► JSFL ──► Animate.exe
        ├──► tools/symbol.py     ──► JSFL ──► Animate.exe
        ├──► tools/keyframe.py   ──► JSFL ──► Animate.exe
        ├──► tools/bone.py       ──► JSFL ──► Animate.exe
        ├──► tools/tween.py      ──► JSFL ──► Animate.exe
        ├──► tools/audio.py      ──► JSFL ──► Animate.exe
        ├──► tools/camera.py     ──► JSFL ──► Animate.exe
        └──► tools/render.py     ──► JSFL ──► Animate.exe

   orchestrator/ also imports from tools/ directly to script the
   full per-shot sequence without needing Claude in the loop for
   production batch runs.
```

## Reading order for someone joining

1. `docs/PLAN.md` for the architecture
2. `docs/RIG_SPEC_v1.md` for the rig contract (the foundation
   everything assumes)
3. `mcp_server/README.md` for MCP details
4. `tests/_smoke_animate_cc.py` for an end-to-end example (once
   Phase 3i+ ships)

## Build status

See `docs/PHASE_3_ROADMAP.md` for what's shipped vs pending.

As of Phase 3o-code (2026-05-17): the rig-consuming MCP tool
(`import_character_rig`) is shipped. `shot_processor` now imports
a character rig's full library into the target .fla and places an
instance on the timeline when `CharacterConfig.rig_fla_path` is
set, instead of warning-and-skipping (the prior placeholder
behavior). MCP tool count: 27. SERVER_VERSION: 0.9.0. Phase
3o-validation (real Jethalal rig + end-to-end smoke) is gated on
the operator commissioning a rigger.
