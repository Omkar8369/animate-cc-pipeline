// hello_world.jsfl — Phase 3b smoke template
//
// Creates an empty Animate CC document (1920x1080, 25 FPS), saves
// it to {{OUTPUT_PATH}}, and closes. Used by the JSFL bridge smoke
// test to verify Animate.exe can be driven from Python.
//
// Substitutions expected:
//   {{OUTPUT_PATH}}   Absolute path where the .fla should be saved.
//                     Windows paths with backslashes are OK; this
//                     script converts to URI via FLfile.platformPathToURI.

// Create a new document with our standard production dimensions.
var doc = fl.createDocument();
doc.width = 1920;
doc.height = 1080;
doc.frameRate = 25;

// Convert the Windows-style path to the file:// URI form that
// fl.saveDocumentAs expects on Windows.
var outputPath = "{{OUTPUT_PATH}}";
var outputURI = FLfile.platformPathToURI(outputPath);

// Save and close.
fl.saveDocumentAs(doc, outputURI);
fl.closeDocument(doc, false);
