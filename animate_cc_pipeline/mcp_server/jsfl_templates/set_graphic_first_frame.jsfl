// set_graphic_first_frame.jsfl
//
// Find the first element on layer {{LAYER_NAME}} at frame
// {{FRAME}} (1-indexed) and set its `firstFrame` + `loop` props.
// Used to drive rotation-strip Graphic Symbols — pose-angle from
// estimation maps to a frame index in the strip.
//
// Substitutions:
//   {{FLA_PATH}}              Path to existing .fla.
//   {{LAYER_NAME}}            Layer holding the Graphic Symbol instance.
//   {{FRAME}}                 1-indexed frame number.
//   {{TARGET_FIRST_FRAME}}    0-indexed frame within the Graphic Symbol
//                             to display (JSFL convention).
//   {{LOOP_MODE}}             "loop", "play once", or "single frame".
//   {{SENTINEL_PATH}}         Sentinel file.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();
var frameIdx0 = ({{FRAME}}) - 1;
if (frameIdx0 < 0) frameIdx0 = 0;

for (var i = 0; i < timeline.layers.length; i++) {
    if (timeline.layers[i].name === "{{LAYER_NAME}}") {
        var frames = timeline.layers[i].frames;
        if (frameIdx0 < frames.length && frames[frameIdx0].elements.length > 0) {
            var elem = frames[frameIdx0].elements[0];
            // Only Graphic Symbol instances have firstFrame.
            // For other element types this assignment is a no-op or
            // silent no-throw in JSFL.
            elem.firstFrame = {{TARGET_FIRST_FRAME}};
            elem.loop = "{{LOOP_MODE}}";
        }
        break;
    }
}

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
