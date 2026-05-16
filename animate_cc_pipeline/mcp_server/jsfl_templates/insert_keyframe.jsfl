// insert_keyframe.jsfl
//
// Insert a keyframe on layer {{LAYER_NAME}} at frame {{FRAME}}
// (1-indexed). Inherits content from the preceding keyframe.
// Extends the layer with regular frames if needed so the target
// frame exists.
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{LAYER_NAME}}     Layer to insert keyframe on.
//   {{FRAME}}          1-indexed frame number.
//   {{SENTINEL_PATH}}  Sentinel file.
//
// API notes (Animate 2020):
//   - Timeline.insertKeyframe(N) requires the target frame to exist
//     and the right layer to be selected. We use convertToKeyframes
//     instead, which is more explicit about its range and works on
//     the selected layer.
//   - Use setSelectedLayers (UI selection) + currentLayer (edit
//     cursor); some JSFL ops use one, some use the other.
//   - Layer extension via insertFrames must happen FIRST, otherwise
//     convertToKeyframes silently no-ops on out-of-range frames.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();
var frameIdx0 = ({{FRAME}}) - 1;
if (frameIdx0 < 0) frameIdx0 = 0;

for (var i = 0; i < timeline.layers.length; i++) {
    if (timeline.layers[i].name === "{{LAYER_NAME}}") {
        timeline.currentLayer = i;
        timeline.setSelectedLayers(i);

        // Extend the layer with regular (non-keyframe) frames so the
        // target frame index actually exists.
        var layerLen = timeline.layers[i].frames.length;
        if (frameIdx0 >= layerLen) {
            timeline.currentFrame = layerLen - 1;
            timeline.insertFrames((frameIdx0 - layerLen) + 1, false);
        }

        // Position the playhead, then convert that one frame to a
        // keyframe (inherits content from preceding keyframe).
        timeline.currentFrame = frameIdx0;
        timeline.convertToKeyframes(frameIdx0, frameIdx0 + 1);
        break;
    }
}

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
