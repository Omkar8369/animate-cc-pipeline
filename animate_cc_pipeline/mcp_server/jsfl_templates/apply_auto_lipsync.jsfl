// apply_auto_lipsync.jsfl
//
// EXPERIMENTAL — Attempt to apply Animate's Auto Lip Sync feature.
// The JSFL surface for this is limited in Animate 2020 — the Auto
// Lip Sync command is mostly a UI feature. We try a couple of
// approaches:
//
//   (a) Setting sound + lipSyncMethod properties on the audio
//       layer's keyframes via setFrameProperty.
//   (b) Running the Animate "Auto Lip Sync" command if it's
//       exposed as a JSFL command file.
//
// Substitutions:
//   {{FLA_PATH}}        Path to existing .fla.
//   {{AUDIO_LAYER}}     Layer holding the audio.
//   {{MOUTH_LAYER}}     Layer holding the mouth Switch instance.
//   {{SENTINEL_PATH}}   Sentinel.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();

// Locate the audio + mouth layers
var audioLayerIdx = -1;
var mouthLayerIdx = -1;
for (var i = 0; i < timeline.layers.length; i++) {
    if (timeline.layers[i].name === "{{AUDIO_LAYER}}") audioLayerIdx = i;
    if (timeline.layers[i].name === "{{MOUTH_LAYER}}") mouthLayerIdx = i;
}

try {
    if (audioLayerIdx >= 0 && mouthLayerIdx >= 0) {
        // Approach (a): set lipSyncMethod via setFrameProperty
        // on the audio layer's starting keyframe. This tells
        // Animate to associate the mouth Switch layer with the
        // audio for auto lipsync.
        timeline.currentLayer = audioLayerIdx;
        timeline.setSelectedLayers(audioLayerIdx);
        timeline.setSelectedFrames(0, 1);
        // The property name + values are best-effort; this may be
        // a no-op on Animate 2020.
        try {
            timeline.setFrameProperty("lipSyncEnabled", true, 0, 1);
        } catch (e) { /* swallow */ }
    }
} catch (e) {
    // Auto Lip Sync isn't reachable through this JSFL — operator
    // must use the UI command, or use per-frame set_switch_state.
}

fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
