// remove_keyframe.jsfl
//
// Clear the keyframe status of frame {{FRAME}} on layer
// {{LAYER_NAME}} (1-indexed). The frame slot remains but now
// extends from the prior keyframe.
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{LAYER_NAME}}     Layer holding the keyframe.
//   {{FRAME}}          1-indexed frame number of the keyframe.
//   {{SENTINEL_PATH}}  Sentinel file.
//
// API notes (Animate 2020):
//   `Timeline.clearKeyframes(start, end)` with explicit range
//   arguments hangs JSFL on Animate 2020 (a dialog or silent
//   failure — symptom: subprocess timeout). The selection-based
//   form works: setSelectedFrames(start, end), then
//   clearKeyframes() with no args operates on the current
//   selection.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();
var frameIdx0 = ({{FRAME}}) - 1;
if (frameIdx0 < 0) frameIdx0 = 0;

for (var i = 0; i < timeline.layers.length; i++) {
    if (timeline.layers[i].name === "{{LAYER_NAME}}") {
        timeline.currentLayer = i;
        timeline.setSelectedLayers(i);
        timeline.setSelectedFrames(frameIdx0, frameIdx0 + 1);
        timeline.currentFrame = frameIdx0;
        timeline.clearKeyframes();
        break;
    }
}

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
