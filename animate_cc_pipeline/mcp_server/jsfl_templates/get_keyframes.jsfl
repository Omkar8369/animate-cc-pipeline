// get_keyframes.jsfl
//
// READ-only: enumerate keyframes on layer {{LAYER_NAME}} and write
// the result as JSON to {{OUT_JSON_PATH}}.
//
// Output JSON shape:
//   {
//     "layer_found": true/false,
//     "keyframes": [1, 10, 20, ...]   // 1-indexed frame numbers
//   }
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{LAYER_NAME}}     Layer to enumerate.
//   {{OUT_JSON_PATH}}  Where the result JSON goes (Python reads it).
//   {{SENTINEL_PATH}}  Sentinel file.
//
// JSFL keyframe detection:
//   timeline.layers[i].frames[j].startFrame === j  iff frame j is
//   the START of a keyframe (Frame objects with the same startFrame
//   belong to the same extended keyframe span).

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();

var layerFound = false;
var keyframes = [];

for (var i = 0; i < timeline.layers.length; i++) {
    if (timeline.layers[i].name === "{{LAYER_NAME}}") {
        layerFound = true;
        var frames = timeline.layers[i].frames;
        for (var j = 0; j < frames.length; j++) {
            if (frames[j].startFrame === j) {
                keyframes.push(j + 1);  // convert to 1-indexed
            }
        }
        break;
    }
}

// Hand-roll JSON (JSFL has no JSON module)
var kfStr = "[";
for (var k = 0; k < keyframes.length; k++) {
    if (k > 0) kfStr += ",";
    kfStr += keyframes[k];
}
kfStr += "]";

var json = "{"
    + '"layer_found":' + (layerFound ? "true" : "false") + ','
    + '"keyframes":' + kfStr
    + "}";

FLfile.write(FLfile.platformPathToURI("{{OUT_JSON_PATH}}"), json);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
