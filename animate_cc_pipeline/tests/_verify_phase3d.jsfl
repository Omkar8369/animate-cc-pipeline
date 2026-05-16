// _verify_phase3d.jsfl
//
// Read back the transform of the first element on layer "BG" at
// frame 1 of {{FLA_PATH}}; write it as JSON to {{OUT_JSON_PATH}}
// for the smoke to assert against. Writes a sentinel to
// {{SENTINEL_PATH}} when done.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();

var out = {x: null, y: null, scaleX: null, scaleY: null, rotation: null, found: false};

for (var i = 0; i < timeline.layers.length; i++) {
    if (timeline.layers[i].name === "BG") {
        var frame = timeline.layers[i].frames[0];
        if (frame && frame.elements.length > 0) {
            var elem = frame.elements[0];
            out.x = elem.x;
            out.y = elem.y;
            out.scaleX = elem.scaleX;
            out.scaleY = elem.scaleY;
            out.rotation = elem.rotation;
            out.found = true;
        }
        break;
    }
}

// Serialize JSON by hand (JSFL doesn't ship a JSON library)
var json = "{"
    + '"x":' + out.x + ','
    + '"y":' + out.y + ','
    + '"scaleX":' + out.scaleX + ','
    + '"scaleY":' + out.scaleY + ','
    + '"rotation":' + out.rotation + ','
    + '"found":' + (out.found ? "true" : "false")
    + "}";

FLfile.write(FLfile.platformPathToURI("{{OUT_JSON_PATH}}"), json);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
