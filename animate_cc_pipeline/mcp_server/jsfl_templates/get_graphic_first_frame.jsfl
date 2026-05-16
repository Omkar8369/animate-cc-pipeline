// get_graphic_first_frame.jsfl
//
// READ-only: extract firstFrame + loop of the first element on
// {{LAYER_NAME}} at frame {{FRAME}}. Writes result JSON to
// {{OUT_JSON_PATH}}.
//
// Output JSON shape:
//   {
//     "found": true|false,
//     "firstFrame": int|null,
//     "loop": string|null,
//     "instanceType": string|null
//   }
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{LAYER_NAME}}     Layer to inspect.
//   {{FRAME}}          1-indexed frame number.
//   {{OUT_JSON_PATH}}  Where Python reads the result.
//   {{SENTINEL_PATH}}  Sentinel file.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();
var frameIdx0 = ({{FRAME}}) - 1;
if (frameIdx0 < 0) frameIdx0 = 0;

var found = false;
var firstFrame = "null";
var loop = "null";
var instanceType = "null";

for (var i = 0; i < timeline.layers.length; i++) {
    if (timeline.layers[i].name === "{{LAYER_NAME}}") {
        var frames = timeline.layers[i].frames;
        if (frameIdx0 < frames.length && frames[frameIdx0].elements.length > 0) {
            var elem = frames[frameIdx0].elements[0];
            found = true;
            firstFrame = (typeof elem.firstFrame === "number") ? elem.firstFrame : "null";
            loop = elem.loop ? '"' + elem.loop + '"' : "null";
            instanceType = elem.instanceType ? '"' + elem.instanceType + '"' : "null";
        }
        break;
    }
}

var json = "{"
    + '"found":' + (found ? "true" : "false") + ','
    + '"firstFrame":' + firstFrame + ','
    + '"loop":' + loop + ','
    + '"instanceType":' + instanceType
    + "}";

FLfile.write(FLfile.platformPathToURI("{{OUT_JSON_PATH}}"), json);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
