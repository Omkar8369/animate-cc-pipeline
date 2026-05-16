// import_image.jsfl
//
// Open the .fla, add a new layer at the top of the timeline,
// import a PNG/JPG file onto frame {{FRAME}} of that layer, save,
// close. Writes a sentinel.
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{IMAGE_PATH}}     Path to PNG or JPG to import.
//   {{LAYER_NAME}}     Name for the new layer (e.g. "BG").
//   {{FRAME}}          1-indexed frame number to insert image on.
//   {{SENTINEL_PATH}}  Sentinel file path.
//
// API notes (Animate 2020):
//   - Layer ops live on Timeline, NOT Document:
//       doc.getTimeline().addNewLayer(name, layerType)
//     `doc.addNewLayer` does NOT exist (confirmed Phase 3c).
//   - addNewLayer auto-selects the new layer as the active one.
//   - importFile(uri, false) places the imported asset on stage
//     at the current frame of the current layer.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();

// Add a new layer at the top of the timeline. It becomes active.
timeline.addNewLayer("{{LAYER_NAME}}", "normal");

// Seek to the target frame (1-indexed → 0-indexed).
var frameIdx0 = ({{FRAME}}) - 1;
if (frameIdx0 < 0) frameIdx0 = 0;
timeline.currentFrame = frameIdx0;

// Import the image onto the stage. importFile(URI, importToLibrary=false)
// places the asset on the current layer + frame and also registers it
// in the Library.
doc.importFile(FLfile.platformPathToURI("{{IMAGE_PATH}}"), false);

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
