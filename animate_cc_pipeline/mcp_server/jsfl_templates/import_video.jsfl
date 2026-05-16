// import_video.jsfl
//
// Open the .fla, add a new layer, import an MP4 as embedded video
// onto frame {{FRAME}} of that layer, save, close. Writes a
// sentinel.
//
// Animate may show an "Import Video" wizard for some MP4s asking
// embed vs link; for short MP4s (animatic shots, ~5-30s) Animate
// 2020 typically embeds without prompting. If the wizard appears
// and blocks JSFL, the Python bridge will time out and force-kill.
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{MP4_PATH}}       Path to MP4 file.
//   {{LAYER_NAME}}     Name for the new layer.
//   {{FRAME}}          1-indexed frame to insert video on.
//   {{SENTINEL_PATH}}  Sentinel file path.
//
// API notes: see import_image.jsfl. Layer creation is on Timeline,
// not Document.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();

timeline.addNewLayer("{{LAYER_NAME}}", "normal");

var frameIdx0 = ({{FRAME}}) - 1;
if (frameIdx0 < 0) frameIdx0 = 0;
timeline.currentFrame = frameIdx0;

doc.importFile(FLfile.platformPathToURI("{{MP4_PATH}}"), false);

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
