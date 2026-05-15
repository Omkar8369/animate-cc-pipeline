// hello_world.jsfl — Phase 3b smoke template
//
// Creates an empty Animate CC document (1920x1080, 25 FPS), saves
// it to {{OUTPUT_PATH}}, writes a completion sentinel to
// {{SENTINEL_PATH}}, then attempts to quit Animate.
//
// We DO NOT depend on fl.quit() to actually terminate Animate.exe —
// in Animate 2020, fl.quit() often hangs behind Welcome/Save dialogs.
// Instead, the JSFL writes a sentinel file; the Python side polls for
// that sentinel + the expected output, then force-kills Animate.exe.
//
// Substitutions expected:
//   {{OUTPUT_PATH}}   Absolute Windows path where the .fla should be
//                     saved (forward slashes OK).
//   {{SENTINEL_PATH}} Absolute Windows path for the completion
//                     sentinel file. Python polls for this.

// Create a new document with our standard production dimensions.
var doc = fl.createDocument();
doc.width = 1920;
doc.height = 1080;
doc.frameRate = 25;

// Save the new .fla to disk.
//
// NB: must be `fl.saveDocument(doc, URI)` — NOT `fl.saveDocumentAs`
// which ignores the URI parameter and opens the interactive Save-As
// dialog. Confirmed in Animate 2020.
var outputURI = FLfile.platformPathToURI("{{OUTPUT_PATH}}");
fl.saveDocument(doc, outputURI);

// Close the document.
fl.closeDocument(doc, false);

// Write the completion sentinel AFTER the output exists. Python's
// poll loop watches for this — once it appears, Python force-kills
// Animate.exe. We do not rely on fl.quit() actually exiting.
var sentinelURI = FLfile.platformPathToURI("{{SENTINEL_PATH}}");
FLfile.write(sentinelURI, "done");

// Try to quit cleanly. If a dialog blocks, the Python force-kill
// takes over.
fl.quit();
