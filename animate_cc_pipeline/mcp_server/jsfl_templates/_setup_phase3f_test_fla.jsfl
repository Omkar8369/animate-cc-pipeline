// _setup_phase3f_test_fla.jsfl
//
// Smoke test helper — builds a .fla that contains a Graphic Symbol
// named "RotationStrip" with 3 blank keyframes, with an instance of
// it placed on a layer "ARM" at frame 1 of the main timeline.
//
// This lets the Phase 3f smoke exercise set_graphic_first_frame
// and get_graphic_first_frame on real Animate state without
// requiring a hand-built rig.
//
// Substitutions:
//   {{FLA_PATH}}       Path where the constructed .fla is saved.
//   {{SENTINEL_PATH}}  Sentinel file.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var library = doc.library;

// 1) Create a new Graphic Symbol called "RotationStrip"
library.addNewItem("graphic", "RotationStrip");

// 2) Descend into it and give it 3 blank keyframes
library.editItem("RotationStrip");
var symbolTimeline = doc.getTimeline();
symbolTimeline.setSelectedLayers(0);
// The new graphic starts with 1 frame at index 0; add 2 more keyframes
symbolTimeline.currentFrame = 0;
symbolTimeline.insertFrames(2, false);  // extend to 3 frames total
symbolTimeline.convertToBlankKeyframes(1, 3);  // make frames 1 and 2 keyframes

// 3) Return to main scene
fl.getDocumentDOM().exitEditMode();

// 4) Add a layer named "ARM" on the main timeline + place the
// RotationStrip instance at (300, 200)
var mainTimeline = doc.getTimeline();
mainTimeline.addNewLayer("ARM", "normal");
library.selectItem("RotationStrip");
library.addItemToDocument({x: 300, y: 200});

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
