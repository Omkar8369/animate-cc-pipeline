// export_png_sequence.jsfl
//
// Export the .fla's timeline as a PNG sequence using Animate's
// per-frame PNG export. Python (via imageio-ffmpeg) then encodes
// these PNGs into an MP4. This two-stage approach avoids Animate's
// native MP4 codec licensing issues.
//
// If START_FRAME_IDX0 / END_FRAME_IDX0 are >= 0, exports only that
// range; otherwise exports the entire timeline.
//
// Substitutions:
//   {{FLA_PATH}}              Path to existing .fla.
//   {{PNG_PREFIX_PATH}}       Output prefix; Animate appends a
//                             numeric suffix + ".png" per frame.
//                             Forward-slash absolute path.
//   {{START_FRAME_IDX0}}      0-indexed start frame, or -1 = all.
//   {{END_FRAME_IDX0}}        0-indexed end frame (inclusive), or -1 = all.
//   {{SENTINEL_PATH}}         Sentinel file (written when done).

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
var timeline = doc.getTimeline();

var startIdx = {{START_FRAME_IDX0}};
var endIdx = {{END_FRAME_IDX0}};

var totalFrames = 0;
if (timeline.layers.length > 0) {
    for (var li = 0; li < timeline.layers.length; li++) {
        if (timeline.layers[li].frames.length > totalFrames) {
            totalFrames = timeline.layers[li].frames.length;
        }
    }
}

if (startIdx < 0) startIdx = 0;
if (endIdx < 0 || endIdx >= totalFrames) endIdx = totalFrames - 1;

// Export each frame individually as PNG. Animate's
// Document.exportPNG(URI, bCurrentPNGSettings, bCurrentFrame)
// exports the CURRENT frame when bCurrentFrame=true. We loop.
//
// File naming: {{PNG_PREFIX_PATH}}NNNN.png with N = 4-digit
// zero-padded 1-based frame index.
//
// (Some Animate versions support exportPNG(uri, opts, false) to
// auto-export ALL frames, but the per-frame naming is unpredictable
// across versions. The loop is verbose but deterministic.)

function pad4(n) {
    var s = "" + (n + 1);
    while (s.length < 4) s = "0" + s;
    return s;
}

for (var f = startIdx; f <= endIdx; f++) {
    timeline.currentFrame = f;
    var outURI = FLfile.platformPathToURI("{{PNG_PREFIX_PATH}}" + pad4(f) + ".png");
    try {
        doc.exportPNG(outURI, true, true);
    } catch (e) {
        // Skip a failing frame rather than abort entire export;
        // Python will count the resulting frames.
    }
}

fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
