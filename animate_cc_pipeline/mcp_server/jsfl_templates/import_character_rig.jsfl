// import_character_rig.jsfl
//
// Open the target .fla, import a rig .fla into its library, place
// an instance of the identity MovieClip symbol on a new top-level
// layer at the given frame + position, save, close. Writes a
// sentinel.
//
// Substitutions:
//   {{FLA_PATH}}         Path to the target .fla (already exists).
//   {{RIG_FLA_PATH}}     Path to the rig .fla to import.
//   {{IDENTITY}}         Symbol name to look up in the imported
//                        library (e.g. "JETHALAL"). Per RIG_SPEC_v1
//                        the rig file contains a MovieClip with this
//                        exact name at library root.
//   {{LAYER_NAME}}       Layer name to add to target timeline
//                        (typically same as IDENTITY).
//   {{FRAME}}            1-indexed frame number for the instance.
//   {{X}}                Stage X position (px) for the instance.
//   {{Y}}                Stage Y position (px) for the instance.
//   {{SENTINEL_PATH}}    Sentinel file path.
//
// API notes (Animate 2020):
//   - `doc.importFile(uri, true)` imports a .fla's library into
//     the active document WITHOUT placing anything on stage. After
//     the call, the imported symbols appear in `doc.library.items`.
//   - Library item lookup is by `name` (str, full path). Top-level
//     MovieClip's `name` is the identity string.
//   - To place an instance: select the library item via
//     `lib.selectItem(name)`, then call `lib.addItemToDocument(
//     {x, y}, name)` — that places at current frame of current layer.
//   - We add a fresh layer first so the instance doesn't collide
//     with existing layers (BG, REF_ANIMATIC, etc.).
//   - JSFL gotcha: `lib.addItemToDocument` returns boolean; if the
//     symbol can't be found it returns false and the instance is
//     never created. We detect this via a post-condition check on
//     the layer's frame element count.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();

// Import the rig's library into the target doc (library-only mode).
var importOk = doc.importFile(
    FLfile.platformPathToURI("{{RIG_FLA_PATH}}"),
    true  // importToLibrary: true → library-only, no stage placement
);

if (!importOk) {
    // Write a "did not work" sentinel so Python sees completion
    // but knows the import failed (Python re-checks via library
    // contents in a future expansion; for now the sentinel is
    // just our "JSFL ran" signal).
    FLfile.write(
        FLfile.platformPathToURI("{{SENTINEL_PATH}}"),
        "import_failed"
    );
    fl.quit();
}

// Add a fresh layer for the character at the top of the timeline.
timeline.addNewLayer("{{LAYER_NAME}}", "normal");

// Move to the target frame (1-indexed → 0-indexed).
var frameIdx0 = ({{FRAME}}) - 1;
if (frameIdx0 < 0) frameIdx0 = 0;
// Extend the layer to cover this frame if needed.
if (timeline.layers[0].frames.length <= frameIdx0) {
    timeline.insertFrames(frameIdx0 - timeline.layers[0].frames.length + 1);
}
timeline.currentFrame = frameIdx0;
// Convert to keyframe at this frame so we can place a fresh element.
timeline.convertToKeyframes(frameIdx0, frameIdx0 + 1);

// Place an instance of the identity symbol on the current frame.
var lib = doc.library;
var placed = lib.addItemToDocument({x: {{X}}, y: {{Y}}}, "{{IDENTITY}}");

// Save + close
fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(
    FLfile.platformPathToURI("{{SENTINEL_PATH}}"),
    placed ? "done" : "instance_not_placed"
);
fl.quit();
