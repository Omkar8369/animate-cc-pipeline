// insert_blank_keyframe.jsfl
//
// Insert a BLANK keyframe (no content) on layer {{LAYER_NAME}} at
// frame {{FRAME}} (1-indexed). Extends the layer if needed.
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{LAYER_NAME}}     Layer to insert blank keyframe on.
//   {{FRAME}}          1-indexed frame number.
//   {{SENTINEL_PATH}}  Sentinel file.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();
var frameIdx0 = ({{FRAME}}) - 1;
if (frameIdx0 < 0) frameIdx0 = 0;

for (var i = 0; i < timeline.layers.length; i++) {
    if (timeline.layers[i].name === "{{LAYER_NAME}}") {
        timeline.currentLayer = i;
        timeline.setSelectedLayers(i);

        var layerLen = timeline.layers[i].frames.length;
        if (frameIdx0 >= layerLen) {
            timeline.currentFrame = layerLen - 1;
            timeline.insertFrames((frameIdx0 - layerLen) + 1, false);
        }

        timeline.currentFrame = frameIdx0;
        timeline.convertToBlankKeyframes(frameIdx0, frameIdx0 + 1);
        break;
    }
}

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
