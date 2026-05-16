// add_classic_tween.jsfl
//
// Add a Classic Tween starting at frame {{START_FRAME}} on layer
// {{LAYER_NAME}}. Animate interpolates position / rotation / scale /
// color to the next keyframe on the same layer.
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{LAYER_NAME}}     Layer holding the starting keyframe.
//   {{START_FRAME}}    1-indexed frame number of the keyframe.
//   {{SENTINEL_PATH}}  Sentinel file.
//
// API notes (Animate 2020, learned in Phase 3g):
//   `Frame.tweenType` is READ-ONLY in JSFL. Direct assignment
//   `frame.tweenType = "motion"` silently no-ops. The right way to
//   add a Classic Tween starting at a keyframe is:
//     timeline.currentLayer = i;
//     timeline.currentFrame = startIdx0;
//     timeline.createMotionTween();
//   This affects the current keyframe + extends to the next
//   keyframe on the same layer.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();
var startIdx0 = ({{START_FRAME}}) - 1;
if (startIdx0 < 0) startIdx0 = 0;

for (var i = 0; i < timeline.layers.length; i++) {
    if (timeline.layers[i].name === "{{LAYER_NAME}}") {
        timeline.currentLayer = i;
        timeline.setSelectedLayers(i);
        timeline.currentFrame = startIdx0;
        timeline.createMotionTween();
        break;
    }
}

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
