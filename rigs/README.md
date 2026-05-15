# rigs/

Character rig `.fla` files for the Animate CC Pipeline.

**Every rig in this directory MUST conform to `docs/RIG_SPEC_v1.md`.**
The validator (`animate_cc_pipeline/rig_contracts/rig_validator.py`,
ships in Phase 3f) enforces this — non-conforming rigs cannot enter
production.

## Layout

```
rigs/
├── README.md                       ← you are here
├── _template/
│   └── template_character.fla      ← (Phase 3f) reference rig
├── jethalal.fla                    ← (Phase 3o) first production rig
├── tappu.fla                       ← future
├── daya.fla                        ← future
└── ...
```

## Naming

`<identity_lowercase>.fla` where `<identity>` matches the character's
`identity` field in `characters.json`. Examples:
`jethalal.fla`, `tappu.fla`, `daya.fla`, `champaklal.fla`.

## How to add a new rig

1. **Read `docs/RIG_SPEC_v1.md`** — this is the contract
2. **Hire a rigger** familiar with Adobe Animate's Armature + Switch
   layers (typically a Moho/Animate freelance rigger)
3. **Provide them with:**
   - Character model sheet (multiple angles, full color)
   - `docs/RIG_SPEC_v1.md` as the build brief
   - `rigs/_template/template_character.fla` (Phase 3f) as the
     structural reference
4. **They deliver:** `<identity>.fla` with all required layers,
   bones, switches, rotation strips, metadata
5. **Run the validator:**
   ```bash
   python animate_cc_pipeline/rig_contracts/rig_validator.py rigs/<identity>.fla
   ```
6. **Fix any failures** — validator prints all offenders. Iterate
   with rigger until validation passes
7. **Add the rig** to `characters.json` via the operator HTML form
   (Node 1 captures `rigFilename`)
8. **Smoke test:** run the pipeline on one shot featuring this
   character

## Storage notes

- `.fla` files are binary (ZIP container). They commit fine to git
  but are not diffable; treat them as opaque assets
- Backups: every rig should also live in cloud storage (separate
  from this repo) because rigger work is expensive to redo
- Large rigs (>20 MB) consider Git LFS; small rigs fine as regular
  blobs

## Cost / time expectations

See `docs/RIG_SPEC_v1.md` "Cost / time guidance for riggers"
section.

## Phase status

- Phase 3a (this commit): directory created; empty except for this
  README
- Phase 3f: template rig added
- Phase 3o: first real rig (Jethalal) validated end-to-end
- Future: full cast (24+ characters) over multiple Phase-4 ships
