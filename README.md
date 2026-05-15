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

**Phase 3a — project scaffold + canonical files + 13 locked decisions.**
See [`CLAUDE.md`](CLAUDE.md) status table for full phase progression
3a → 3p.

This is a working-in-public repo. Phases ship one at a time with full
canonical-file sync, drift-grep, and ship discipline (see `CLAUDE.md`).

## Quick start (once Phase 3p ships)

```bash
# 1. Install Adobe Animate CC (2020 or later) on Windows
# 2. Install Python deps (uses embedded Python from ComfyUI portable)
"C:\Users\Omkar Hajare\Desktop\download\ComfyUI_windows_portable\python_embeded\python.exe" \
  -m pip install -r requirements.txt

# 3. Validate environment
python tools/phase3/validate_phase3_env.py

# 4. Register the MCP server in Claude Code
python tools/phase3/install_animate_mcp.py

# 5. Run on a shot
python run_node7_animate.py --shot shot_001 \
    --rough-mp4 shots/shot_001.mp4 \
    --metadata metadata.json \
    --rigs-dir rigs/ \
    --out-dir output/
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
