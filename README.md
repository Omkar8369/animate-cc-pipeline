# Animate CC Pipeline

A production pipeline that converts **rough animatic MP4 shots** into
**clean, reference-accurate 2D animation** using rigged characters
in **Adobe Animate CC**, orchestrated by Claude Code via a custom
**MCP server**.

Built for Indian 2D-cartoon-style daily-strip TV production (TMKOC-flavored).

## What it does

```
ROUGH ANIMATIC (mp4)         CLEAN 2D ANIMATION (mp4)
  rough sketch of                clean rigged characters
  characters in     ────────►    placed exactly where the
  approximate poses              rough showed them, with
  with timing baked in           the rough's exact timing
```

The pipeline:

1. Reads the rough animatic + your metadata (which characters are
   in which positions)
2. Extracts keyposes + per-frame character bboxes
3. Runs pose estimation on every frame
4. Opens Adobe Animate CC, imports your rigged characters
5. Places each rig at the exact pixel location of the rough character
6. Sets bone angles to match the rough's pose
7. Inserts keyframes on every frame; Animate tweens between them
8. Triggers auto lipsync against your Hindi audio
9. Renders to MP4 for animator review

An animator reviews the auto-generated draft and fixes ~10-20% of
frames. Editor takes it from there.

## Why this approach

| Approach | Cost / 22-min episode | Quality | Daily strip viable? |
|----------|----------------------|---------|---------------------|
| Traditional 2D studio | ₹40-70 lakh | Premium | Yes (40-50 people) |
| Pure AI image gen (Flux + LoRA) | ₹2-5 lakh | 70-80% identity | No (inconsistent) |
| Pure AI video gen (Veo/Kling) | ₹3-6 lakh | Variable | Limited |
| **This pipeline (rigged + Claude+MCP)** | **₹50K-1.5L** | **Production-grade** | **Yes (8-12 people)** |

## Status

**Phases 3a–3n + 3o-code + 3p-docs + 3o-adapter shipped.** The MCP
server (27 tools, incl. `import_character_rig`), pose-estimation
node, pose→bone math, end-to-end orchestrator, camera-move detector,
production batch runner, rig-consuming code path, environment
validator, and rig label sidecars (which adapt the rigger's
obfuscated symbol names to operator-friendly labels) are all in. 31
production rigs received from the rigger on 2026-05-17. Remaining
work is Phase 3o-validation (real Jethalal end-to-end Animate.exe
smoke run) and Phase 3p-validation (first real 22-min episode +
production sign-off; gated on 3o-validation). See
[`CLAUDE.md`](CLAUDE.md) status table for full phase progression
3a → 3p.

This is a working-in-public repo. Phases ship one at a time with full
canonical-file sync, drift-grep, and ship discipline (see `CLAUDE.md`).

## Quick start (works today for pure-Python paths; .fla / MP4 work needs a rigger-delivered rig per Phase 3o-validation)

```bash
# 1. Install Adobe Animate CC (2020 or later) on Windows
# 2. Install Python deps (uses embedded Python from ComfyUI portable)
"C:\Users\Omkar Hajare\Desktop\download\ComfyUI_windows_portable\python_embeded\python.exe" \
  -m pip install -r requirements.txt

# 3. Validate environment
python tools/phase3/validate_phase3_env.py

# 4. Register the MCP server in Claude Code
python tools/phase3/install_animate_mcp.py

# 5. Run on a single shot (single-config orchestrator CLI)
python run_node7_animate.py --config batch_config.json

# 6. Run a production batch (with retry + JSONL progress)
python run_batch.py --config batch_config.json \
    --retry-count 2 \
    --jsonl batch_progress.jsonl \
    --report-out batch_report.json

# 7. (optional) Detect camera moves from a frame sequence before
#    assembly, then reference the output in your batch config via
#    `camera_moves_path`:
python run_camera_detect.py --frames-dir frames/shot_001 \
    --shot-id shot_001 --out work/shot_001/camera_moves.json

# 8. (one-time per character rig) Generate a labels sidecar so the
#    pipeline can resolve angle names against the rigger's obfuscated
#    library symbol names:
python tools/phase3/rig_labeler.py --rig rigs/jethalal.fla \
    --character JETHALAL --init
#    Then edit `rigs/jethalal.fla.labels.json` (or
#    `rigs/labels/jethalal.labels.json`) to set the `label` field on
#    each placement to one of: front, front_3q_l, front_3q_r, side_l,
#    side_r, back, back_3q_l, back_3q_r.
python tools/phase3/rig_labeler.py --rig rigs/jethalal.fla --verify
```

## Repository layout

See [`CLAUDE.md`](CLAUDE.md) "Repo map" section for the full directory
tree. Key locations:

- [`CLAUDE.md`](CLAUDE.md) — project context, locked decisions,
  environment gotchas (read this first)
- [`docs/PLAN.md`](docs/PLAN.md) — architecture description
- [`docs/PHASE_3_ROADMAP.md`](docs/PHASE_3_ROADMAP.md) — phase ship plan
- [`docs/RIG_SPEC_v1.md`](docs/RIG_SPEC_v1.md) — rig contract
- [`animate_cc_pipeline/`](animate_cc_pipeline/) — main code
- [`rigs/`](rigs/) — character `.fla` files

## Build discipline

Strict per-phase ship checklist with six canonical files kept in
sync. Detailed in `CLAUDE.md`. The short version:

- One phase per commit
- Update all six canonical files together
- Run drift-grep before commit
- Stage by file name (never `git add -A`)
- Push session branch fast-forward to `origin/main`
- After every push: "Run `git pull` in your main working copy to sync."

## License + IP

This pipeline is a tool. The rigged characters you feed it are your
own IP (or your client's). The pipeline does not redistribute
character art.

## Related repos

- [`animatic-refinement`](../animatic-refinement/) — precursor project
  (11-node AI-generation pipeline). Nodes 1-5 architecture informs this
  repo's design.

## References

- Adobe Animate JSFL API:
  https://help.adobe.com/en_US/as3/iprg/WS5b3ccc516d4fbf351e63e3d118a9b89b65-7fe4.html
- Model Context Protocol: https://modelcontextprotocol.io/
- DWPose: https://github.com/IDEA-Research/DWPose
