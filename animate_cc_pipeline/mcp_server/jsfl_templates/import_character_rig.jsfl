// import_character_rig.jsfl
//
// Cross-fla symbol import via the stage-instance + clipCopy/clipPaste
// workflow. This is the JSFL pattern that actually works in Animate
// 2020 (verified by Phase 3o-validation probes against real
// production rigs).
//
// History (Phase 3o-validation):
//
//   v1: doc.importFile(rigUri, true)              -> wrong API (for media)
//   v2: lib.addItemFromExternalLibrary             -> doesn't exist
//   v3: fl.copyLibraryItem(rigLib, item)           -> "Cannot find file"
//   v4: fl.copyLibraryItem(rigUri, item)           -> returns true but no-op
//   v5 (this): place instance on rig's stage, copy
//              with clipCopy, paste into target.
//              Brings the symbol + ALL library
//              dependencies. Verified working.
//
// Substitutions:
//   {{FLA_PATH}}         Path to the target .fla.
//   {{RIG_FLA_PATH}}     Path to the rig .fla.
//   {{IDENTITY}}         Library item name in the rig.
//   {{LAYER_NAME}}       Layer name to add to target timeline.
//   {{FRAME}}            1-indexed frame number.
//   {{X}}                Stage X position for the pasted instance.
//   {{Y}}                Stage Y position for the pasted instance.
//   {{SENTINEL_PATH}}    Sentinel file path.

var rigUri = FLfile.platformPathToURI("{{RIG_FLA_PATH}}");
var targetUri = FLfile.platformPathToURI("{{FLA_PATH}}");
var sentinelUri = FLfile.platformPathToURI("{{SENTINEL_PATH}}");
// Diagnostic log goes to a SEPARATE file. CRITICAL: must not write
// to the sentinel mid-script — the Python bridge polls for the
// sentinel to exist and force-kills Animate as soon as it does.
var debugUri = FLfile.platformPathToURI("{{DEBUG_LOG_PATH}}");

var diag = [];
function step(msg) {
    diag.push(msg);
    FLfile.write(debugUri, diag.join("\n"));
}

function finalizeSentinel(outcome) {
    diag.push(outcome);
    FLfile.write(debugUri, diag.join("\n"));
    // Only NOW write the sentinel — this triggers the bridge to
    // force-kill Animate.
    FLfile.write(sentinelUri, outcome);
}

// ─── Step 1: Open rig ───────────────────────────────────────────
step("S1.0: about to call fl.openDocument; rigUri=" + rigUri);
var rigDoc = fl.openDocument(rigUri);
step("S1.2: openDocument returned: " + (rigDoc ? "doc-object" : "null"));
if (!rigDoc) {
    finalizeSentinel("import_failed");
    fl.quit();
}
var rigTl = rigDoc.getTimeline();
step("S1.4: getTimeline returned; layers=" + rigTl.layers.length);
var rigLib = rigDoc.library;
step("S1.5: rigLib obtained; about to query items.length");
var rigItemCount = rigLib.items.length;
step("S1.6: rigLib.items.length=" + rigItemCount);

var hasItem = rigLib.itemExists("{{IDENTITY}}");
step("S1.7: itemExists({{IDENTITY}})=" + hasItem);
if (!hasItem) {
    finalizeSentinel("instance_not_placed");
    fl.closeDocument(rigDoc, false);
    fl.quit();
}

// ─── Step 2: Place instance on a fresh isolated layer in rig ───
// addNewLayer returns the INDEX of the new layer. We track that
// explicitly because layers[0] is the TOP of the timeline which
// may or may not be the just-added one depending on context.
step("S2: addNewLayer to rig");
var newLayerIdx = rigTl.addNewLayer("__phase3o_temp__", "normal");
step("S2: new layer index=" + newLayerIdx
     + " currentLayer=" + rigTl.currentLayer
     + " rigTl.layers count now " + rigTl.layers.length);
rigTl.currentFrame = 0;
rigDoc.selectNone();
var placed = rigLib.addItemToDocument({x: 0, y: 0}, "{{IDENTITY}}");
step("S2: addItemToDocument returned " + placed);
if (!placed) {
    finalizeSentinel("instance_not_placed");
    fl.closeDocument(rigDoc, false);
    fl.quit();
}

// ─── Step 3: Verify the placed element exists ──────────────────
// Use the new layer's index (returned by addNewLayer), NOT layers[0]
// which may refer to a pre-existing layer (the rig has 9 layers
// before our addNewLayer call, one per turnaround pose).
var tempLayer = rigTl.layers[newLayerIdx];
step("S3: tempLayer.name=" + tempLayer.name + " frames.length=" + tempLayer.frames.length);
var topFrame = tempLayer.frames[0];
step("S3: tempFrame elements count=" + (topFrame ? topFrame.elements.length : "null"));
if (!topFrame || topFrame.elements.length === 0) {
    step("S3: no element on rig — FAIL");
    finalizeSentinel("instance_not_placed");
    fl.closeDocument(rigDoc, false);
    fl.quit();
}
var newElem = topFrame.elements[topFrame.elements.length - 1];
step("S3: newElem.elementType=" + newElem.elementType
     + " libraryItem.name=" + (newElem.libraryItem ? newElem.libraryItem.name : "(none)"));

// ─── Step 4: Select + clipCopy ─────────────────────────────────
rigDoc.selection = [newElem];
step("S4: selection set; rigDoc.selection.length=" + rigDoc.selection.length);
rigDoc.clipCopy();
step("S4: clipCopy called");

// ─── Step 5: Open target ───────────────────────────────────────
step("S5: opening target " + targetUri);
var targetDoc = fl.openDocument(targetUri);
if (!targetDoc) {
    step("S5: target openDocument returned null — FAIL");
    finalizeSentinel("import_failed");
    fl.closeDocument(rigDoc, false);
    fl.quit();
}
var targetTl = targetDoc.getTimeline();
step("S5: opened; target layers=" + targetTl.layers.length
     + " initial library items=" + targetDoc.library.items.length);

// addNewLayer returns the index of the new layer. Track explicitly
// (same reason as for the rig — layers[0] may not be it).
var targetLayerIdx = targetTl.addNewLayer("{{LAYER_NAME}}", "normal");
step("S5: target addNewLayer idx=" + targetLayerIdx
     + " currentLayer=" + targetTl.currentLayer
     + " layers=" + targetTl.layers.length);

var frameIdx0 = ({{FRAME}}) - 1;
if (frameIdx0 < 0) frameIdx0 = 0;
var newTargetLayer = targetTl.layers[targetLayerIdx];
if (newTargetLayer.frames.length <= frameIdx0) {
    targetTl.currentLayer = targetLayerIdx;
    targetTl.insertFrames(frameIdx0 - newTargetLayer.frames.length + 1);
}
// Move to the target frame BEFORE pasting. The convertToKeyframes
// step (used in placeholder mode) is not needed for paste — pasting
// onto a frame creates the necessary keyframe automatically.
targetTl.currentLayer = targetLayerIdx;
targetTl.currentFrame = frameIdx0;
targetDoc.selectNone();
step("S5: target ready; currentLayer=" + targetTl.currentLayer
     + " currentFrame=" + targetTl.currentFrame);

// ─── Step 6: Paste ─────────────────────────────────────────────
targetDoc.clipPaste();
step("S6: clipPaste called");

// Inspect the layer we just created (NOT layers[0]).
var afterLayer = targetTl.layers[targetLayerIdx];
var afterFrame = afterLayer.frames[frameIdx0];
step("S6: post-paste target layers[" + targetLayerIdx + "].frames["
     + frameIdx0 + "].elements.length="
     + (afterFrame ? afterFrame.elements.length : "null"));
step("S6: post-paste target library items=" + targetDoc.library.items.length);

// Also report the WHOLE timeline state in case paste landed elsewhere
var totalElems = 0;
for (var li = 0; li < targetTl.layers.length; li++) {
    var lyr = targetTl.layers[li];
    for (var fi = 0; fi < lyr.frames.length; fi++) {
        var fr = lyr.frames[fi];
        if (fr && fr.elements && fr.elements.length > 0) {
            totalElems += fr.elements.length;
            step("S6: found " + fr.elements.length + " element(s) at layer["
                 + li + "].frames[" + fi + "] (layer.name=" + lyr.name + ")");
        }
    }
}
step("S6: total elements across target timeline: " + totalElems);

var instancePlaced = afterFrame && afterFrame.elements.length > 0;

if (instancePlaced) {
    var pastedElem = afterFrame.elements[afterFrame.elements.length - 1];
    pastedElem.x = {{X}};
    pastedElem.y = {{Y}};
    step("S7: repositioned to ({{X}},{{Y}})");
}

// ─── Step 8: Save + close ──────────────────────────────────────
fl.saveDocument(targetDoc);
step("S8: saved target");
fl.closeDocument(targetDoc, false);
fl.closeDocument(rigDoc, false);

// Write the final sentinel — this is what tells the Python bridge
// to force-kill Animate.
finalizeSentinel(instancePlaced ? "done" : "instance_not_placed");
fl.quit();
