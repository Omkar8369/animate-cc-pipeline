// _setup_phase3h_test_fla.jsfl
//
// Smoke helper — builds a Switch-style Graphic Symbol called
// "MouthSwitch" with 3 named keyframes (mouth_A, mouth_E, mouth_O),
// then places an instance on layer "MOUTH" frame 1 of the main
// timeline.
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{SENTINEL_PATH}}  Sentinel.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var library = doc.library;

// 1) Create the MouthSwitch Graphic Symbol with 3 keyframes
library.addNewItem("graphic", "MouthSwitch");
library.editItem("MouthSwitch");
var symbolTimeline = doc.getTimeline();
symbolTimeline.setSelectedLayers(0);
symbolTimeline.currentFrame = 0;
symbolTimeline.insertFrames(2, false);            // extend to 3 frames
symbolTimeline.convertToBlankKeyframes(1, 3);      // make frames 1 & 2 keyframes

// Label the three keyframes
var labels = ["mouth_A", "mouth_E", "mouth_O"];
for (var i = 0; i < labels.length; i++) {
    symbolTimeline.currentFrame = i;
    // Frame.labelType + Frame.name are how labels are stored
    // setFrameProperty is the safe mutation path (we learned that
    // Frame.* setters silently fail in many cases on Animate 2020).
    symbolTimeline.setSelectedFrames(i, i + 1);
    symbolTimeline.setFrameProperty("labelType", "name", i, i + 1);
    symbolTimeline.setFrameProperty("name", labels[i], i, i + 1);
}

// 2) Return to main scene
fl.getDocumentDOM().exitEditMode();

// 3) Add layer "MOUTH" + place MouthSwitch instance
var mainTimeline = doc.getTimeline();
mainTimeline.addNewLayer("MOUTH", "normal");
library.selectItem("MouthSwitch");
library.addItemToDocument({x: 200, y: 200});

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
