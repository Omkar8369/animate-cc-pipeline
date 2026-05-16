// set_instance_scale.jsfl
//
// Set scaleX / scaleY of the first element on {{LAYER_NAME}} at
// frame {{FRAME}} (1-indexed). Values like 0.5 (half), 2.0 (double).
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{LAYER_NAME}}     Layer holding the target element.
//   {{FRAME}}          1-indexed frame number.
//   {{SX}}             New scaleX.
//   {{SY}}             New scaleY.
//   {{SENTINEL_PATH}}  Sentinel file.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();
var frameIdx0 = ({{FRAME}}) - 1;
if (frameIdx0 < 0) frameIdx0 = 0;

for (var i = 0; i < timeline.layers.length; i++) {
    if (timeline.layers[i].name === "{{LAYER_NAME}}") {
        var frames = timeline.layers[i].frames;
        if (frameIdx0 < frames.length && frames[frameIdx0].elements.length > 0) {
            var elem = frames[frameIdx0].elements[0];
            elem.scaleX = {{SX}};
            elem.scaleY = {{SY}};
        }
        break;
    }
}

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
