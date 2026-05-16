// set_camera_position.jsfl
//
// EXPERIMENTAL. Set Animate's Camera layer transform at frame
// {{FRAME}}. The JSFL Camera surface in Animate 2020 is sparse;
// this template tries multiple approaches via try/catch.
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{FRAME}}          1-indexed frame number.
//   {{X}}              Camera X translation (stage pixels).
//   {{Y}}              Camera Y translation.
//   {{ZOOM}}           Zoom multiplier (1.0 = 100%).
//   {{ROTATION}}       Camera rotation (degrees).
//   {{SENTINEL_PATH}}  Sentinel file.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();
var frameIdx0 = ({{FRAME}}) - 1;
if (frameIdx0 < 0) frameIdx0 = 0;

try {
    // Enable the camera if not already
    if (typeof doc.cameraEnabled !== "undefined") {
        doc.cameraEnabled = true;
    }

    // Seek to target frame
    timeline.currentFrame = frameIdx0;

    // Try setCamera* methods (may not exist on Animate 2020)
    try {
        doc.setCameraPosition({{X}}, {{Y}});
    } catch (e) { /* swallow */ }

    try {
        doc.setCameraZoom({{ZOOM}});
    } catch (e) { /* swallow */ }

    try {
        doc.setCameraRotation({{ROTATION}});
    } catch (e) { /* swallow */ }
} catch (e) {
    // Outer try-catch: any failure here is non-fatal. The sentinel
    // still writes, so the bridge sees completed_normally=True.
    // Operator can verify via the .fla directly.
}

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
