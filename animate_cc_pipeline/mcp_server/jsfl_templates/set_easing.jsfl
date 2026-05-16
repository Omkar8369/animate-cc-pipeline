// set_easing.jsfl
//
// Set tweenEasing on the keyframe at {{FRAME}} of {{LAYER_NAME}}.
// Range -100..+100; 0 = linear.
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{LAYER_NAME}}     Layer.
//   {{FRAME}}          1-indexed frame number.
//   {{EASING}}         Integer -100..100.
//   {{SENTINEL_PATH}}  Sentinel.
//
// API notes (Animate 2020, learned in Phase 3g):
//   Direct assignment `frame.tweenEasing = N` silently no-ops —
//   `Frame` objects in JSFL appear to be immutable views for tween
//   properties. The working approach is
//   `Timeline.setFrameProperty("tweenEasing", N, start, end)`
//   which actually mutates the live timeline state.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();
var frameIdx0 = ({{FRAME}}) - 1;
if (frameIdx0 < 0) frameIdx0 = 0;

for (var i = 0; i < timeline.layers.length; i++) {
    if (timeline.layers[i].name === "{{LAYER_NAME}}") {
        timeline.currentLayer = i;
        timeline.setSelectedLayers(i);
        timeline.setSelectedFrames(frameIdx0, frameIdx0 + 1);
        timeline.setFrameProperty("tweenEasing", {{EASING}}, frameIdx0, frameIdx0 + 1);
        break;
    }
}

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
