# animate_cc_pipeline/

Main code for the Animate CC Pipeline.

## Layout

- `mcp_server/` — Python MCP server bridging Claude ↔ Animate CC.
  Each subfolder = one category of Animate operations (document,
  symbol, keyframe, bone, tween, audio, camera, render).
- `orchestrator/` — Python-side glue:
  - `cli_node6_pose.py` runs pose estimation (calls RunPod worker)
  - `cli_node7_animate.py` is the main shot orchestrator (drives MCP)
  - `pose_to_bones.py` is joint-coordinates → bone-angles math
  - `shot_processor.py` per-shot driver
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
