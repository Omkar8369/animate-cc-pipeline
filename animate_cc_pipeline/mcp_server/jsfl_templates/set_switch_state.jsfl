// set_switch_state.jsfl
//
// Pin the Graphic Symbol instance on (layer, frame) to its frame
// labeled {{STATE_NAME}}. Sets instance.firstFrame to the matching
// frame index + loop = "single frame".
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{LAYER_NAME}}     Layer holding the Switch Graphic instance.
//   {{FRAME}}          1-indexed frame on main timeline.
//   {{STATE_NAME}}     Frame label inside the Graphic Symbol's
//                      timeline (e.g. "mouth_A", "eyebrows_raised").
//   {{SENTINEL_PATH}}  Sentinel file.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();
var frameIdx0 = ({{FRAME}}) - 1;
if (frameIdx0 < 0) frameIdx0 = 0;

var targetInstance = null;
var libraryItemName = null;

// Find the instance + its underlying library item
for (var i = 0; i < timeline.layers.length; i++) {
    if (timeline.layers[i].name === "{{LAYER_NAME}}") {
        var frames = timeline.layers[i].frames;
        if (frameIdx0 < frames.length && frames[frameIdx0].elements.length > 0) {
            var elem = frames[frameIdx0].elements[0];
            // libraryItem holds the underlying Graphic Symbol
            if (elem.libraryItem) {
                targetInstance = elem;
                libraryItemName = elem.libraryItem.name;
            }
        }
        break;
    }
}

var matchedFrameIdx = -1;
if (libraryItemName) {
    // Descend into the library item to find the frame whose label
    // matches STATE_NAME.
    doc.library.editItem(libraryItemName);
    var symbolTimeline = doc.getTimeline();
    if (symbolTimeline.layers.length > 0) {
        var symbolFrames = symbolTimeline.layers[0].frames;
        for (var j = 0; j < symbolFrames.length; j++) {
            // Frame labels are stored on the keyframe; only check the
            // start of each keyframe to avoid duplicate names from
            // extended frames inheriting the label.
            if (symbolFrames[j].startFrame === j) {
                if (symbolFrames[j].name === "{{STATE_NAME}}") {
                    matchedFrameIdx = j;
                    break;
                }
            }
        }
    }
    // Return to main scene
    fl.getDocumentDOM().exitEditMode();
}

if (matchedFrameIdx >= 0 && targetInstance) {
    targetInstance.firstFrame = matchedFrameIdx;
    targetInstance.loop = "single frame";
}

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
