# Android MediaCodec HEVC Transcode Pipeline

Transcoding video on Android — converting a camera's 4K HEVC clip to a 1080p H.264 file for upload, say — means driving the platform's codec stack directly: extract compressed frames from a container, feed them to a decoder, run the raw frames through a scaler, encode them, and mux the result. `MediaCodec` is the asynchronous state machine at the center of that pipeline, and its contract (buffer or surface modes, async callbacks, EOS signaling) is where hand-rolled transcoders succeed or deadlock. This article covers the full pipeline architecture, the async `MediaCodec` model, surface-to-surface processing, and the failure modes specific to HEVC decode/encode paths.

## Scope

This article addresses Android's `MediaCodec` API as used for transcoding: asynchronous callback mode (`MediaCodec.Callback`), decode-to-surface and encode-from-surface topologies, `MediaExtractor`/`MediaMuxer` container handling, `MediaFormat` configuration for HEVC (H.265) decode and encode, end-of-stream signaling, and dynamic resolution/crop handling. It covers pipeline architecture and correctness. It does not cover DRM-protected media, NDK-level codec usage, or `Transformer` (androidx.media3) higher-level APIs except as architectural comparison.

## Workflow or implementation guidance

The canonical transcode topology for resolution-changing conversion is **surface-to-surface**:

```
MediaExtractor → MediaCodec(decoder, output=Surface of MediaCodec encoder input) → MediaCodec(encoder) → MediaMuxer
```

The decoder renders decoded frames directly onto the encoder's input surface (a `Surface` obtained from `encoder.createInputSurface()`); a `OpenGL` layer in between (or on newer APIs, the codec's scaling) performs resize and any color/pixel-aspect handling; the encoder produces compressed packets that the app writes to a `MediaMuxer`. Buffer-to-buffer (pulling `ByteBuffer` outputs and pushing them to the encoder) is possible for same-codec remuxing but fails for resolution changes and color-format portability — surface mode exists precisely because raw-frame formats vary per device.

The async model. Since API 21, the robust way to drive `MediaCodec` is callback mode:

```java
codec.setCallback(new MediaCodec.Callback() {
  @Override public void onInputBufferAvailable(MediaCodec c, int index) { …dequeue-free feed… }
  @Override public void onOutputBufferAvailable(MediaCodec c, int index, MediaCodec.BufferInfo info) { … }
  @Override public void onOutputFormatChanged(MediaCodec c, MediaFormat fmt) { … }
  @Override public void onError(MediaCodec c, int code, int action) { … }
}, handler);
codec.configure(format, surface, null, 0);
codec.start();
```

Pipeline discipline:

1. **Feed from the extractor on input-available.** Read `MediaExtractor.sample*`, write sample bytes into the input buffer (`codec.getInputBuffer(index)`), set presentation time from `extractor.getSampleTime()`, queue with `queueInputBuffer(index, 0, size, ptsUs, 0)`. When the extractor is exhausted, queue one input buffer with `BUFFER_FLAG_END_OF_STREAM` — EOS propagates downstream.
2. **EOS is a fence, not a flush.** After EOS is queued on input, no more input may be queued until the output side reports EOS (`BufferInfo.flags & BUFFER_FLAG_END_OF_STREAM`). The pipeline drains: decoder emits remaining frames, encoder emits remaining packets, then the encoder's output delivers EOS — the only legitimate completion signal. Polling with timeouts and guessing "it's done" produces truncated tails.
3. **`onOutputFormatChanged` before first output is the muxer contract.** The first callback event for each codec is a format change announcing actual stream parameters (for encoders: csd-0/csd-1 in the format — the codec-specific data HEVC/H.264 need in-band at mux time). The muxer track must be added (`muxer.addTrack(fmt)` returns a track index) *before* writing samples; writing sample data with the CSD from the format as the first buffers is how the output stays playable.
4. **HEVC specifics.** Decoding HEVC needs `MediaFormat.KEY_MIME = "video/hevc"` and the extractor's format (which carries the HVCC configuration). Encoding HEVC (`"video/hevc"` encoder) is device-dependent in availability and bitrate-control quality; many production transcoders decode HEVC but encode H.264 (`"video/avc"`) for compatibility — decide from `MediaCodecList` capability queries, not assumptions.
5. **Configure the encoder deliberately:** `KEY_WIDTH/HEIGHT` (post-scale), `KEY_BIT_RATE` (compute from resolution/framerate with a target quality; ~2× pixels ⇒ ~2× bitrate at same quality), `KEY_FRAME_RATE`, `KEY_I_FRAME_INTERVAL` (1–2 s for streaming targets), `KEY_COLOR_FORMAT` surface-mode handles internally, and `KEY_PROFILE/LEVEL` for device-target constraints. For modern devices, `MediaFormat.KEY_BITRATE_MODE` = `BITRATE_MODE_VBR` with a peak cap is the usual choice.
6. **Rotation and aspect.** Camera clips carry rotation metadata (`KEY_ROTATION`); the transcode must apply it (rotate during the GL pass, then strip/set metadata consistently) or produce sideways video. Pixel aspect ratio and crop rectangles (`KEY_CROP_*` from decoder format changes) likewise: honor crop or you ship black borders.
7. **Backpressure and flow.** Surface mode self-throttles (the Surface fences frame flow to the encoder's consumption rate). In callback mode, never block the codec's handler thread — heavy work (file I/O to the muxer) belongs on a separate executor, with buffers released promptly (`releaseOutputBuffer(index, true/false)`); holding buffers stalls the pipeline silently.

A worked example: compressing a 4K60 HEVC clip to 1080p30 H.264 for upload. Extractor opens the MP4, selects the video track; decoder configured HEVC with encoder's input surface; a GL pass downsamples 3840×2160 → 1920×1080 (dropping every other frame via pts filtering for 30 fps); encoder configured AVC at ~8 Mbps VBR, I-frame every 2 s; muxer writes track + samples; EOS propagates extractor → decoder → (surface) → encoder → muxer completion. The three correctness details that most often break this in the field: EOS fence handling (truncated files), CSD ordering at mux start (unplayable output on some players), and rotation metadata (sideways output from portrait cameras).

Higher-level alternative worth knowing: androidx.media3's `Transformer` implements exactly this pipeline with tested edge handling; hand-rolled `MediaCodec` remains the path when you need custom GL effects, sub-second clip processing, or control the library can't express. The failure-mode knowledge below applies to both — `Transformer` surfaces the same codec errors.

## Controls

- Capability-gate at runtime: query `MediaCodecList`/`MediaCodecInfo` for HEVC decode/encode and the target profile before offering a transcode path; fall back per device matrix.
- Test on the device matrix, not one flagship: codec behavior (color formats, CSD quirks, error codes) varies by vendor; a CI farm smoke-transcoding a canonical test clip (portrait, rotated, HEVC, odd SAR) per API level catches the variance.
- Assert output integrity in tests: parse the produced file with `MediaExtractor`, check duration within tolerance of input, decodable first/last frames, and track metadata (rotation, dimensions) matches intent.
- Instrument stall detection: a watchdog on inter-callback latency (no output buffer N seconds after input EOS ⇒ report codec/driver state) turns silent hangs into telemetry.
- Handle `MediaCodec.CodecException` with `isRecoverable`/`isTransient` branches: transient ⇒ wait/retry, recoverable ⇒ reset codec state, else fail with user-facing guidance (e.g., unsupported profile).

## Validation evidence

- The asynchronous callback model, buffer/surface modes, `createInputSurface`, EOS flag semantics, `MediaFormat` keys (MIMEs for `video/hevc`/`video/avc`, bitrate/frame-rate/I-frame/color/profile keys), `MediaCodecList` capability queries, and `CodecException` recoverability semantics are specified in the Android Developers `MediaCodec` reference documentation and the supported media formats guide published by Google.
- `MediaExtractor`/`MediaMuxer` track/sample/CSD handling is documented in their respective Android API references.
- A reproducible validation harness: transcode a canonical clip (known duration, rotation, SAR) on-device; assert (a) completion fired on EOS only, (b) output track format matches configured encoder parameters, (c) frame count ≈ input (± drops applied), (d) duration within one-frame tolerance — four assertions that catch the four most common pipeline bugs.

## Failure modes and correction

- **Truncated output.** Cause: pipeline torn down before encoder EOS. Correct by strict EOS-fence discipline; completion is an event, never a timeout guess.
- **Unplayable file on some players.** Cause: muxer track added late or CSD buffers misordered. Correct by add-track-on-format-change and writing CSD buffers first.
- **Sideways/black-bordered output.** Cause: rotation/crop/SAR ignored. Correct by honoring decoder format changes in the GL pass and writing correct metadata.
- **Pipeline freeze mid-stream.** Cause: blocking the callback handler or holding buffers. Correct by executor offload and prompt buffer release; watchdog converts freezes to diagnostics.
- **Codec init failures on some devices.** Cause: profile/level or HEVC-encode unavailability. Correct by capability gating with fallback matrix.

## Limitations

- Codec availability and quality are device/vendor-dependent; no contract guarantees HEVC encode or specific bitrate-mode behavior.
- Surface-mode pipelines run opaque to frame content; per-pixel operations require the GL layer (or Image API in buffer mode) with its own portability costs.
- DRM-protected inputs are not transcodable by design.
- Very long files need streaming memory discipline (extractor/muxer are file-backed; decoded surfaces are not the bottleneck, but app-side buffering must stay bounded).

## Canonical sources

- Google, Android Developers — MediaCodec API reference (async callbacks, surface mode, formats, EOS): https://developer.android.com/reference/android/media/MediaCodec
- Google, Android Developers — Supported media formats (HEVC/H.264 encode-decode matrices): https://developer.android.com/media/platform/supported-formats
