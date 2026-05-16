// create_doc.jsfl
//
// Create a new Animate CC document, set canvas + frame rate, save
// to {{FLA_PATH}}, then close. Writes a completion sentinel to
// {{SENTINEL_PATH}} so the Python bridge knows when JSFL is done.
//
// Best-effort fl.quit() at the end — the bridge force-kills
// Animate.exe once the sentinel appears, so we don't depend on
// quit actually working.
//
// Substitutions:
//   {{FLA_PATH}}       Absolute path (forward slashes OK) where the
//                      new .fla should be saved.
//   {{SENTINEL_PATH}}  Absolute path for the completion sentinel.
//   {{WIDTH}}          Canvas width in pixels (integer).
//   {{HEIGHT}}         Canvas height in pixels (integer).
//   {{FPS}}            Frame rate (integer).

var doc = fl.createDocument();
doc.width = {{WIDTH}};
doc.height = {{HEIGHT}};
doc.frameRate = {{FPS}};

fl.saveDocument(doc, FLfile.platformPathToURI("{{FLA_PATH}}"));
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
