// set_instance_rotation.jsfl
//
// Set rotation (degrees, clockwise positive) of the first element
// on {{LAYER_NAME}} at frame {{FRAME}} (1-indexed).
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{LAYER_NAME}}     Layer holding the target element.
//   {{FRAME}}          1-indexed frame number.
//   {{ANGLE}}          Rotation in degrees.
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
            elem.rotation = {{ANGLE}};
        }
        break;
    }
}

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
