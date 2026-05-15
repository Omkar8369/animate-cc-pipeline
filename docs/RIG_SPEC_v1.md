# Rig Specification v1

**Status:** Locked 2026-05-14 as part of Phase 3a.

This document defines the contract every character rig (`.fla` file)
must follow to be usable by the Animate CC Pipeline. The
`rig_validator.py` script (ships in Phase 3f) enforces this contract.
**A rig that fails validation cannot enter production — no exceptions.**

This contract is the foundation that makes Claude+MCP orchestration
possible. Without standardized layer / bone / switch naming, Claude
cannot drive multiple characters' rigs generically.

## Audience

- **Rigger building a new character**: this is your build spec.
- **Operator hiring a rigger**: include this document in the brief.
- **Developer extending the validator**: this is the source of truth.
- **Claude Code orchestrating**: tool functions assume this spec.

## Top-level rig structure

A conforming `.fla` file contains exactly ONE top-level Movie Clip
named `<IDENTITY>_RIG` (where `<IDENTITY>` matches the character's
`identity` from `characters.json` in upper-case, e.g.,
`JETHALAL_RIG`, `TAPPU_RIG`).

This Movie Clip's timeline contains:

- Layers organized in the spec'd hierarchy (below)
- A single keyframe at frame 1 holding the character's **default
  pose** (neutral standing, arms at sides, looking forward)

## Required layer hierarchy

Top-level layers inside `<IDENTITY>_RIG`, ordered top-to-bottom in
the Animate timeline (top = furthest forward visually):

```
head                  ← head + face (group)
  ├── face            ← face Switch layer (expressions)
  │   ├── expression_neutral
  │   ├── expression_happy
  │   ├── expression_angry
  │   ├── expression_shocked
  │   ├── expression_sad
  │   └── expression_squint
  ├── eyes            ← eyes Switch layer (states)
  │   ├── eyes_open
  │   ├── eyes_closed
  │   ├── eyes_wide
  │   └── eyes_squint
  ├── mouth           ← mouth Switch layer (lipsync phonemes)
  │   ├── mouth_neutral
  │   ├── mouth_A
  │   ├── mouth_E
  │   ├── mouth_I
  │   ├── mouth_O
  │   ├── mouth_U
  │   ├── mouth_M     ← bilabial closed
  │   ├── mouth_F     ← labiodental
  │   └── mouth_L     ← tongue visible
  ├── eyebrows        ← Switch layer
  │   ├── eyebrows_neutral
  │   ├── eyebrows_raised
  │   ├── eyebrows_furrowed
  │   └── eyebrows_quizzical
  └── hair            ← static or animated hair layer

neck                  ← single drawing

torso                 ← torso (front-facing default)
  └── torso_rotation_strip   ← optional Graphic Symbol with
                                rotation states for body twist

arm_L_upper           ← upper arm (left, character's anatomical)
  └── arm_L_upper_rotation_strip  ← REQUIRED if arm needs dynamic
                                     poses; Graphic Symbol with 8
                                     frames at 0/45/90/135/180/225/
                                     270/315 degrees

arm_L_lower           ← forearm + hand
  └── arm_L_lower_rotation_strip  ← REQUIRED, 8 frames

arm_R_upper           ← upper arm (right)
  └── arm_R_upper_rotation_strip  ← REQUIRED, 8 frames

arm_R_lower           ← forearm + hand
  └── arm_R_lower_rotation_strip  ← REQUIRED, 8 frames

leg_L_upper           ← thigh (left)
leg_L_lower           ← shin + foot
leg_R_upper
leg_R_lower

hips                  ← static
shoulders             ← static (or torso-attached)

(optional)
hat_or_accessory      ← top-most layer for hats / glasses
prop_left_hand        ← parented to arm_L_lower
prop_right_hand       ← parented to arm_R_lower
```

## Layer naming rules

- ASCII only, lowercase, snake_case
- `_L` / `_R` suffix denotes character's anatomical left / right
  (NOT viewer's left / right)
- Switch-state child names follow `<parent>_<state>` (e.g.,
  `mouth_A`, `eyebrows_raised`)
- Rotation strip naming: `<part>_rotation_strip` for the inner
  Graphic Symbol that holds the per-angle drawings

## Required bones

The rig MUST have an Armature ("IK skeleton") with bones named
identically to their corresponding layers:

```
bone_torso              (root)
├── bone_neck
│   └── bone_head
├── bone_shoulder_L
│   └── bone_arm_L_upper
│       └── bone_arm_L_lower
├── bone_shoulder_R
│   └── bone_arm_R_upper
│       └── bone_arm_R_lower
├── bone_hip_L
│   └── bone_leg_L_upper
│       └── bone_leg_L_lower
└── bone_hip_R
    └── bone_leg_R_upper
        └── bone_leg_R_lower
```

Bone pivot points:

- `bone_head` pivots at neck-attachment point
- `bone_arm_*_upper` pivots at shoulder joint
- `bone_arm_*_lower` pivots at elbow joint
- `bone_leg_*_upper` pivots at hip joint
- `bone_leg_*_lower` pivots at knee joint
- `bone_torso` pivots at hip center

## Required Switch states for mouths (Hindi lipsync)

Animate's Auto Lip Sync feature maps phonemes to mouth states. The
following names MUST exist in the `mouth` Switch layer:

| State name | Phoneme group | Animate visemes mapped to it |
|------------|---------------|------------------------------|
| `mouth_neutral` | rest / silence | Ⓡ |
| `mouth_A` | "aa", "ah" | AAA, AH |
| `mouth_E` | "e", "eh" | EE |
| `mouth_I` | "i", "ee" | IH |
| `mouth_O` | "o", "oh" | OH |
| `mouth_U` | "u", "oo" | UH |
| `mouth_M` | bilabials (m, b, p) | MBP |
| `mouth_F` | labiodentals (f, v) | FV |
| `mouth_L` | dentals (l, n, t, d) | L |

For Hindi: vowel set maps cleanly to mouth_A/E/I/O/U. Aspirated
consonants (kh, gh, ch, th, dh, ph, bh) snap to the unaspirated
counterpart's viseme. Retroflex consonants (ट ठ ड ढ) snap to
`mouth_L`.

## Required Switch states for expressions (minimum set)

- `eyes`: `_open`, `_closed`, `_wide`, `_squint`
- `eyebrows`: `_neutral`, `_raised`, `_furrowed`, `_quizzical`
- `face`: `_neutral`, `_happy`, `_angry`, `_shocked`, `_sad`,
  `_squint`

A rig MAY include additional states (e.g., `_smug`, `_terrified`)
but the minimum set above is mandatory.

## Rotation strip specification

For each limb that needs dynamic-pose support (all four arm
parts), the layer contains a single Graphic Symbol instance
named `<part>_rotation_strip`. The Graphic Symbol's timeline has
exactly **8 keyframes** at frames 1-8, each showing the limb at
a specific rotation:

| Frame | Angle (degrees) | Direction |
|-------|-----------------|-----------|
| 1 | 0 | straight down |
| 2 | 45 | forward-down |
| 3 | 90 | forward |
| 4 | 135 | forward-up |
| 5 | 180 | straight up |
| 6 | 225 | back-up |
| 7 | 270 | back |
| 8 | 315 | back-down |

JSFL sets the instance's `firstFrame` property to select which angle
shows. Rotation strips are MANDATORY for arm parts in v1; legs are
recommended but optional (sitcom legs rarely do extreme rotations).

## Pivot conventions

- Rig origin (0, 0) at character's **feet center** (midpoint between
  ankle bones) when in default pose
- Default pose: character standing, facing forward, arms at sides
- Y axis grows UP (Animate convention; documenting because some math
  needs explicit awareness)
- All bone pivots match anatomical joint locations

## Required metadata (frame 1 of timeline, hidden metadata layer)

A locked layer named `_metadata` at the top of the rig contains a
text field with a JSON blob:

```json
{
  "rig_spec_version": 1,
  "identity": "JETHALAL",
  "default_height_units": 600,
  "default_shoulder_width_units": 250,
  "head_pivot_offset": [0, -540],
  "feet_pivot_offset": [0, 0],
  "rotation_strip_angle_step": 45,
  "rotation_strip_frame_count": 8,
  "mouth_switch_path": "head/mouth",
  "expression_switch_path": "head/face",
  "eyes_switch_path": "head/eyes",
  "eyebrows_switch_path": "head/eyebrows",
  "required_bones": [
    "bone_torso", "bone_neck", "bone_head",
    "bone_arm_L_upper", "bone_arm_L_lower",
    "bone_arm_R_upper", "bone_arm_R_lower",
    "bone_leg_L_upper", "bone_leg_L_lower",
    "bone_leg_R_upper", "bone_leg_R_lower"
  ],
  "notes": "Free-text rigger notes about this character's quirks"
}
```

The validator parses this on rig load. Values populate the orchestrator's
math (scale calculations, head-anchored position, etc.).

## Naming the rig file

`<identity_lowercase>.fla` — e.g., `jethalal.fla`, `tappu.fla`,
`daya.fla`. Lives in `rigs/` directory.

## Validator behavior

`rig_validator.py` (Phase 3f) loads the rig and checks:

1. Top-level `<IDENTITY>_RIG` Movie Clip exists
2. All required layers present with exact names
3. All required Switch states present
4. All required bones present in armature
5. Rotation strips have correct 8-frame structure
6. `_metadata` layer present with valid JSON
7. Metadata identity matches filename
8. Default pose visually plausible (frame 1 has bones at expected
   angles — straight torso, arms down, etc.; checked via bone angle
   ranges)

Failures print all offenders (not just the first) for one-pass
fixup. Exit code 1 on any failure.

## Versioning + future changes

If `RIG_SPEC` needs to change incompatibly:

- Bump to `RIG_SPEC_v2.md` (new file, don't edit v1)
- Validator gains `--spec-version` flag
- New rigs target v2; existing v1 rigs stay supported via
  validator's v1 path
- 6-month deprecation window before dropping v1 support
- Migration script provided for v1→v2 where automatable

Additive changes (new optional states, new metadata fields with
defaults) DO NOT require version bump.

## Reference rig

Phase 3f ships `rigs/_template/template_character.fla` — a
mechanically-complete stick figure that validates. Use it as the
structural reference when building real character rigs.

## Cost / time guidance for riggers (informational)

- First conforming character rig: 4-6 weeks for an experienced
  Moho/Animate rigger working freelance (~₹2-3 lakh)
- Subsequent characters using same body type / proportions: 1-2 weeks
  each (~₹60K-1L)
- Variant characters (different proportions, e.g., a child vs an
  adult): closer to first-character pricing
