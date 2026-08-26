# browser-webcodecs-whip-streaming

**Issue:** Our near-zero-cost creator streaming research needs an architecture where a creator goes live from a plain browser tab — no OBS, no Streamlabs, no desktop software. The pipeline we validated: the browser's WebCodecs API encodes AV1/Opus (or H.264 fallback) directly, media is ingested over HTTP-flavored signaling (WHIP, RFC 9725) or a raw WebSocket/WebTransport bridge into a Cloudflare Worker, the Worker packages the stream into HLS segments, writes them to R2, and viewers play through the CDN. This article captures the verified architecture, the WebCodecs encoder constraints that decide codec choice, the WHIP protocol mechanics including where the media plane can and cannot terminate, and how to run a bitrate ladder entirely from the browser.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why browser-side encoding kills the "creator needs streaming software" requirement

1. **The encoder is already on the viewer's machine.** Every Chromium-based browser since 94, Firefox 130+, and Safari 26 ships WebCodecs (`VideoEncoder`/`AudioEncoder`), giving web pages direct access to the same hardware/software codecs that desktop streaming software wraps. By 2026 this is baseline cross-browser API surface, not a flag.
2. **No install, no config export, no update treadmill.** OBS-style tools require download, scene setup, codec knowledge, and per-machine tuning; a WebCodecs page ships the encoder config as JavaScript, so the platform upgrades every creator simultaneously on deploy. The creator interaction collapses to "click Go Live and grant camera/mic."
3. **Source capture is native to the platform.** `getUserMedia`, `getDisplayMedia`, canvas capture, and Web Audio all produce frames/audio the page can route into an encoder without any OS-level virtual camera — screen share, co-streaming a remote video onto a canvas, or overlaying graphics are all DOM operations.
4. **Economics, not just UX.** Because encoding happens on the creator's device and packaging is a few Worker CPU-ms per segment, the marginal serving cost of a small-creator platform reduces to R2 operations + storage (R2 egress to viewers is free), which is the basis of the project's ~$9/month-for-100-creators cost model.

## The pipeline end to end

1. **Capture.** `getUserMedia`/`getDisplayMedia` yields a `MediaStream`; a `MediaStreamTrackProcessor` (or canvas frame pump) turns video into `VideoFrame`s, and a Web Audio `AudioWorklet` turns mic data into `AudioData` chunks.
2. **Encode.** One or more `VideoEncoder` instances (one per ladder rung — see ladder section below) plus an `AudioEncoder` (Opus) consume the frames. `VideoEncoderConfig.latencyMode: "realtime"` and small `GOP` sizes keep segment cadence stable for HLS.
3. **Transport — two honest shapes.** (a) *WHIP shape*: the page runs an `RTCPeerConnection` against a WHIP endpoint (RFC 9725); Cloudflare Stream exposes native WHIP live inputs, and since March 13 2025 Stream's WHIP/WHEP implementation is powered by Cloudflare Realtime. (b) *BYO-HLS shape*: the page muxes encoded chunks itself (or a Worker does) over WebSocket/WebTransport, and a Worker writes fMP4/CMAF segments + the playlist directly to R2. Shape (b) is the only one where "the Worker packages into HLS" is literally true end to end.
4. **The Worker's role.** In the WHIP shape the Worker brokers auth and mints short-lived WHIP URLs/tokens for Stream live inputs, then Stream does HLS packaging; in the BYO-HLS shape the Worker receives encoded chunks, timestamps and muxes them, writes segments to R2 (`ctx.env.BUCKET.put`), and rewrites the playlist atomically. In both shapes the Worker owns access control, per-creator keys, and viewer session policy.
5. **Delivery.** Viewers hit the R2-backed HLS through a Workers route or R2 custom domain with CDN caching in front; the player is standard hls.js. In the WHIP-to-Stream shape, Stream's own HLS/DASH endpoints and player cover delivery.

## WebCodecs encoder configuration and constraints (hardware vs software AV1)

1. **`hardwareAcceleration` is a preference, not a guarantee.** `VideoEncoderConfig.hardwareAcceleration` accepts `"no-preference"` (default), `"prefer-hardware"`, or `"prefer-software"` — the UA may still fall back, and the W3C issue tracker shows ongoing debate (w3c/webcodecs#896) about what `isConfigSupported()` should echo back for this field.
2. **Always probe with `VideoEncoder.isConfigSupported()` using real parameters.** Support varies by codec string, resolution, framerate, and bitrate together (w3c/webcodecs#492; Chromium issue #<number> shows hw encode reporting unsupported above 1080p30 on some devices). Probe with your actual `av01.*` string, width/height, and framerate — never assume from codec name alone.
3. **AV1 encode is not uniform across browsers.** Chromium exposes libaom software AV1 encoding plus hardware AV1 on GPUs that have it; real-world datasets (webcodecsfundamentals.org) show Safari frequently reports no AV1 encode support at all. Ship a codec waterfall: AV1 hw → AV1 sw → VP9/H.264 hw → H.264 baseline, chosen at runtime from probe results.
4. **H.264 is the compatibility floor, AV1 is the bandwidth prize.** AV1 at a given bitrate saves roughly 30-40% versus H.264, which matters when the creator's uplink is a phone; but H.264 hardware encoders are near-universal, so the waterfall terminates reliably. Opus audio encoding is supported everywhere WebCodecs is.
5. **Realtime-relevant config knobs.** `latencyMode: "realtime"`, `bitrateMode: "variable"`, an explicit `framerate`, and keyframe interval control (`GOP` in frames) are the levers that keep HLS segmenting deterministic; leaving defaults tuned for file encoding shows up as stuttering segment boundaries and ballooming latency.
6. **Reconfiguration means a new encoder.** WebCodecs has no live reconfigure of codec/resolution; changing the ladder rung means draining the queue, closing the encoder, and constructing a new one with the new config. Plan keyframe-aligned handoffs so the HLS discontinuity is clean.

## WHIP (RFC 9725) mechanics and the Worker media-plane reality

1. **The protocol is deliberately tiny.** WHIP (published February 2025 as RFC 9725, from the IETF WISH working group) is: HTTP POST an SDP offer to an endpoint URL → receive a `201 Created` with an SDP answer body and a `Location` header naming a session resource → later `DELETE` that session resource to hang up. Bearer tokens in the `Authorization` header are the common auth model, which is exactly what a Worker wants to mint and validate.
2. **WHIP signaling terminates fine in a Worker; SRTP does not.** The media plane of a WHIP session is standard WebRTC — ICE, DTLS, SRTP over UDP — which a plain Worker cannot terminate. So "WHIP ingest to a Worker" in practice means the Worker serves (or fronts) the HTTP signaling endpoint while the actual media lands on something that speaks WebRTC: Cloudflare Stream live inputs (native WHIP), Cloudflare Realtime/Calls, or your own media server (see `cloudflare/mediamtx-vps-alternative.md`).
3. **You cannot inject raw WebCodecs output into an RTCPeerConnection.** `RTCRtpScriptTransform`/WebRTC Encoded Transform can only modify frames already flowing through a sender's pipeline — there is no supported path to stuff arbitrary WebCodecs-encoded AV1 into RTP. The WHIP shape therefore uses WebRTC's own internal encoder (controlled via sender `encodingParameters`), while WebCodecs-driven custom encoding belongs to the BYO-HLS shape. Design for this split instead of fighting it.
4. **In the WHIP shape, browser-side ladder control is simulcast.** `addTransceiver` with multiple `sendEncodings` (per-encoding `maxBitrate`, `scaleResolutionDownBy`) plus degradation preference gives the edge the rungs to choose from; the edge/SFU or Stream decides which rung lands in HLS.
5. **Cloudflare-specific notes.** Stream accepts WHIP at live inputs directly (docs: developers.cloudflare.com/stream/webrtc-beta/), the March 2025 changelog records the migration of Stream Live WHIP/WHEP onto the Realtime-backed implementation, and `cloudflare/cloudflare-calls-webrtc.md` in this KB covers the Calls-side API if you build on Realtime directly.

## Bitrate ladder control from the browser

1. **One `VideoFrame`, N encoders.** A single frame from the capture source can be `encode()`d by multiple `VideoEncoder` instances with different width/height (frames can be constructed/cropped cheaply) and bitrate — that is the entire ladder, running on the creator's silicon, costing the platform nothing per rung.
2. **Adapt to the uplink from encoder telemetry.** `encodeQueueDepth` and per-chunk `byteLength` trends are the congestion signals you already have in-page: when the queue grows across consecutive windows, drop to a lower rung (new encoder, keyframe-aligned) and/or reduce `bitrate`; when it stays empty and the link is good, step up.
3. **Segment duration is the cost and latency lever.** In the BYO-HLS shape, every segment is one R2 Class A write and every playlist rewrite is another; longer segments (e.g. 6s vs 2s) cut write volume proportionally at the price of viewer latency, and R2 lifecycle rules on short TTLs (hours, not months) keep storage spend near zero. These two levers dominate the monthly bill at 100-creator scale.
4. **Keyframe alignment across rungs.** Cut segments at keyframes and start each rung's encoder on the same frame timestamps so all renditions of a segment share boundaries — otherwise the player cannot switch rungs cleanly and your analytics drift.

## Gotchas

1. **The "WHIP in a Worker" trap.** A Worker can answer the SDP POST, but if nothing terminates ICE/SRTP behind it, every client hangs in `iceConnectionState: checking`. Pick the media plane (Stream, Realtime, MediaMTX) before writing signaling code.
2. **The probe-once trap.** Codec support is per-device and per-parameter; cache nothing across devices and re-probe after user-facing errors rather than shipping a static support matrix.
3. **The tabs-throttle trap.** Background tabs get timer-throttled and capture can stall; keep the encoder driven by frame callbacks (not `setInterval`) and warn creators when `document.visibilityState` changes mid-stream.
4. **The VAD-chop trap.** Aggressive `latencyMode: "realtime"` audio config can drop leading silence; verify the first seconds of speech after Go Live with a real recording before declaring victory.

## Related

- `cloudflare/cloudflare-calls-webrtc.md` — Calls/Realtime sessions and WHIP/WHEP signaling
- `cloudflare/stream-best-practices.md` — Stream product basics
- `cloudflare/r2-best-practices.md`, `cloudflare/r2-lifecycle-rules.md` — cost control for segment stores
- `cloudflare/mediamtx-vps-alternative.md` — when this path hits limits
- RFC 9725: https://www.rfc-editor.org/info/rfc9725/
- W3C WebCodecs: https://www.w3.org/TR/webcodecs/
- MDN Codec selection: https://developer.mozilla.org/en-US/docs/Web/API/WebCodecs_API/Codec_selection
- CF Stream WebRTC/WHIP: https://developers.cloudflare.com/stream/webrtc-beta/
- CF Stream changelog (Realtime migration): https://developers.cloudflare.com/stream/changelog/
