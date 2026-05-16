// import_audio.jsfl
//
// Import an audio file (WAV/MP3/AIFF) into the .fla's library and
// place an instance on layer {{LAYER_NAME}} at frame {{FRAME}}.
// Auto-creates the layer if missing.
//
// Substitutions:
//   {{FLA_PATH}}       Path to existing .fla.
//   {{AUDIO_PATH}}     Path to audio file (WAV/MP3/AIFF).
//   {{LAYER_NAME}}     Layer for the audio placement.
//   {{FRAME}}          1-indexed frame number.
//   {{SENTINEL_PATH}}  Sentinel file.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();
var audioURI = FLfile.platformPathToURI("{{AUDIO_PATH}}");

// Find or create the audio layer
var layerIdx = -1;
for (var i = 0; i < timeline.layers.length; i++) {
    if (timeline.layers[i].name === "{{LAYER_NAME}}") {
        layerIdx = i;
        break;
    }
}
if (layerIdx === -1) {
    timeline.addNewLayer("{{LAYER_NAME}}", "normal");
    layerIdx = 0;  // new layer is at top
}
timeline.currentLayer = layerIdx;
timeline.setSelectedLayers(layerIdx);

// Seek to target frame; extend layer if needed
var frameIdx0 = ({{FRAME}}) - 1;
if (frameIdx0 < 0) frameIdx0 = 0;
var layerLen = timeline.layers[layerIdx].frames.length;
if (frameIdx0 >= layerLen) {
    timeline.currentFrame = layerLen - 1;
    timeline.insertFrames((frameIdx0 - layerLen) + 1, false);
}
timeline.currentFrame = frameIdx0;

// importFile(URI, importToLibrary=false) imports the file AND places
// an instance on the current frame of the current layer. For audio
// files Animate places the sound's waveform on the layer frame.
doc.importFile(audioURI, false);

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
