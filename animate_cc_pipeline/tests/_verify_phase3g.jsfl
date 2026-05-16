// _verify_phase3g.jsfl
//
// Read back tween properties of a frame and write as JSON.
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{LAYER_NAME}}     Layer to inspect.
//   {{FRAME}}          1-indexed frame number.
//   {{OUT_JSON_PATH}}  Where the result JSON is written.
//   {{SENTINEL_PATH}}  Sentinel.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();
var frameIdx0 = ({{FRAME}}) - 1;
if (frameIdx0 < 0) frameIdx0 = 0;

var tweenType = "null";
var tweenEasing = "null";
var found = false;

for (var i = 0; i < timeline.layers.length; i++) {
    if (timeline.layers[i].name === "{{LAYER_NAME}}") {
        var frames = timeline.layers[i].frames;
        if (frameIdx0 < frames.length) {
            var fr = frames[frameIdx0];
            found = true;
            tweenType = fr.tweenType ? '"' + fr.tweenType + '"' : "null";
            tweenEasing = (typeof fr.tweenEasing === "number")
                ? fr.tweenEasing : "null";
        }
        break;
    }
}

var json = "{"
    + '"found":' + (found ? "true" : "false") + ','
    + '"tweenType":' + tweenType + ','
    + '"tweenEasing":' + tweenEasing
    + "}";

FLfile.write(FLfile.platformPathToURI("{{OUT_JSON_PATH}}"), json);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
