// add_motion_tween.jsfl
//
// Create a modern Motion Tween span on layer {{LAYER_NAME}} from
// {{START_FRAME}} to {{END_FRAME}} via Timeline.createMotionObject.
// EXPERIMENTAL on Animate 2020 — newer JSFL APIs have shown gotchas.
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{LAYER_NAME}}     Layer.
//   {{START_FRAME}}    1-indexed frame number (start).
//   {{END_FRAME}}      1-indexed frame number (end, inclusive).
//   {{SENTINEL_PATH}}  Sentinel file.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();
var startIdx0 = ({{START_FRAME}}) - 1;
var endIdx0 = ({{END_FRAME}}) - 1;
if (startIdx0 < 0) startIdx0 = 0;

for (var i = 0; i < timeline.layers.length; i++) {
    if (timeline.layers[i].name === "{{LAYER_NAME}}") {
        timeline.currentLayer = i;
        timeline.setSelectedLayers(i);
        timeline.setSelectedFrames(startIdx0, endIdx0 + 1);
        // createMotionObject takes the selected-frame range from
        // setSelectedFrames; some versions accept explicit args too.
        try {
            timeline.createMotionObject(startIdx0, endIdx0);
        } catch (e) {
            // If createMotionObject doesn't exist or errors, the
            // sentinel still writes — caller will inspect and may
            // fall back to add_classic_tween.
        }
        break;
    }
}

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
