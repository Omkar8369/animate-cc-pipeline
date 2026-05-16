// place_symbol_instance.jsfl
//
// Place an instance of an existing library symbol onto a layer at
// the given stage coordinates and frame.
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{SYMBOL_NAME}}    Name of library item to instance.
//   {{LAYER_NAME}}     Layer to place on (auto-created if missing).
//   {{FRAME}}          1-indexed frame number.
//   {{X}}              Stage X coord.
//   {{Y}}              Stage Y coord.
//   {{SENTINEL_PATH}}  Sentinel file.
//
// API notes:
//   - library.itemExists(name)        — boolean
//   - library.selectItem(name)        — selects the named item
//   - library.addItemToDocument({x,y}) — adds an instance of the
//     selected library item to the current frame of the current
//     layer at stage coords {x,y}.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();

// Find or create the target layer
var layerIdx = -1;
for (var i = 0; i < timeline.layers.length; i++) {
    if (timeline.layers[i].name === "{{LAYER_NAME}}") {
        layerIdx = i;
        break;
    }
}
if (layerIdx === -1) {
    timeline.addNewLayer("{{LAYER_NAME}}", "normal");
    layerIdx = 0;  // new layer becomes top + active
}
timeline.currentLayer = layerIdx;

// Seek to the target frame (1-indexed → 0-indexed)
var frameIdx0 = ({{FRAME}}) - 1;
if (frameIdx0 < 0) frameIdx0 = 0;
timeline.currentFrame = frameIdx0;

// Ensure there is a keyframe at the target frame
var existingFrames = timeline.layers[layerIdx].frames.length;
if (frameIdx0 >= existingFrames) {
    timeline.insertBlankKeyframe(frameIdx0);
}

// Select the library item and add an instance to the document
if (doc.library.itemExists("{{SYMBOL_NAME}}")) {
    doc.library.selectItem("{{SYMBOL_NAME}}");
    doc.library.addItemToDocument({x: {{X}}, y: {{Y}}});
}

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
