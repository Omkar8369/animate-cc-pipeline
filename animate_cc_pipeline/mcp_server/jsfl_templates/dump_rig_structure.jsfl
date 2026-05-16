// dump_rig_structure.jsfl
//
// READ-only: extract the rig's structural metadata as JSON and
// write to {{OUT_JSON_PATH}}. Consumed by Python `rig_validator.py`.
//
// Output JSON shape:
//   {
//     "library_items": [
//       {
//         "name": "JETHALAL_RIG",
//         "kind": "movie clip",
//         "frame_count": 1,
//         "layers": [
//           { "name": "head", "kind": "normal", "text_content": "" },
//           { "name": "_metadata", "kind": "normal",
//             "text_content": "{...metadata json...}" },
//           ...
//         ]
//       },
//       {
//         "name": "arm_L_upper_rotation_strip",
//         "kind": "graphic",
//         "frame_count": 8
//       },
//       ...
//     ]
//   }
//
// Substitutions:
//   {{FLA_PATH}}       Path to .fla to inspect.
//   {{OUT_JSON_PATH}}  Where the structure JSON is written.
//   {{SENTINEL_PATH}}  Sentinel file.
//
// JSON serialization is hand-rolled because JSFL has no JSON
// library. We aggressively escape strings to keep the output
// parseable on the Python side.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var library = doc.library;

function jsonEscape(s) {
    if (typeof s !== "string") return "";
    var r = "";
    for (var i = 0; i < s.length; i++) {
        var c = s.charAt(i);
        var code = s.charCodeAt(i);
        if (c === '"') r += '\\"';
        else if (c === "\\") r += "\\\\";
        else if (c === "\n") r += "\\n";
        else if (c === "\r") r += "\\r";
        else if (c === "\t") r += "\\t";
        else if (code < 32) r += "\\u" + ("0000" + code.toString(16)).slice(-4);
        else r += c;
    }
    return r;
}

function classifyKind(item) {
    // item.itemType is "movie clip" / "graphic" / "button" / "bitmap"
    //                  / "sound" / "video" / "folder" / "font" / "component"
    return item.itemType || "unknown";
}

// We can only inspect Movie Clip / Graphic Symbol internals by
// editing them. We descend into each item to count frames + layers,
// then return to the main scene.

var dump = [];

for (var i = 0; i < library.items.length; i++) {
    var item = library.items[i];
    var kind = classifyKind(item);
    var entry = {
        name: item.name,
        kind: kind,
        frame_count: 0,
        layers: []
    };

    if (kind === "movie clip" || kind === "graphic") {
        // Enter the symbol's timeline
        library.editItem(item.name);
        var symbolTimeline = doc.getTimeline();
        entry.frame_count = (symbolTimeline.layers.length > 0)
            ? symbolTimeline.layers[0].frames.length
            : 0;
        for (var j = 0; j < symbolTimeline.layers.length; j++) {
            var layer = symbolTimeline.layers[j];
            var textContent = "";
            // Check if first frame has a text element (e.g. for _metadata layer)
            if (layer.frames.length > 0 && layer.frames[0].elements.length > 0) {
                var firstElem = layer.frames[0].elements[0];
                if (firstElem.elementType === "text") {
                    var lines = firstElem.textRuns;
                    if (lines && lines.length > 0) {
                        for (var k = 0; k < lines.length; k++) {
                            if (lines[k].characters) textContent += lines[k].characters;
                        }
                    }
                }
            }
            entry.layers.push({
                name: layer.name,
                kind: layer.layerType || "normal",
                text_content: textContent
            });
        }
        // Exit edit mode — return to Scene 1
        fl.getDocumentDOM().exitEditMode();
    }
    dump.push(entry);
}

// Serialize the dump array to JSON manually
function serializeLayer(l) {
    return '{'
        + '"name":"' + jsonEscape(l.name) + '",'
        + '"kind":"' + jsonEscape(l.kind) + '",'
        + '"text_content":"' + jsonEscape(l.text_content) + '"'
        + '}';
}

function serializeEntry(e) {
    var layerJsons = [];
    for (var i = 0; i < e.layers.length; i++) {
        layerJsons.push(serializeLayer(e.layers[i]));
    }
    return '{'
        + '"name":"' + jsonEscape(e.name) + '",'
        + '"kind":"' + jsonEscape(e.kind) + '",'
        + '"frame_count":' + e.frame_count + ','
        + '"layers":[' + layerJsons.join(",") + ']'
        + '}';
}

var entries = [];
for (var i = 0; i < dump.length; i++) {
    entries.push(serializeEntry(dump[i]));
}
var json = '{"library_items":[' + entries.join(",") + ']}';

FLfile.write(FLfile.platformPathToURI("{{OUT_JSON_PATH}}"), json);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
