# mediamtx-vps-alternative

**Issue:** The Cloudflare browser-encoder path (`cloudflare/browser-webcodecs-whip-streaming.md`) is near-free at small scale, but it hits hard limits: WHIP ingest terminates on Cloudflare's WebRTC implementation (Stream/Realtime) rather than ours, codec choice is bounded by what the edge accepts (H.265 and other non-WebRTC-native codecs are effectively out), per-minute Stream delivery pricing scales worse than raw bandwidth at volume, and provider rate/feature limits are not negotiable. This article records MediaMTX (formerly rtsp-simple-server) as the verified self-hosted VPS alternative: a single zero-dependency Go binary that speaks WHIP/WHEP, WebRTC, SRT, RTSP, RTMP, HLS, MPEG-TS, RTP, and Media-over-QUIC — plus the GPU-less CPU reality of self-hosting and a decision table for when the VPS beats the edge and when it loses.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Verified MediaMTX capabilities

1. **One binary, no runtime.** MediaMTX (github.com/bluenviron/mediamtx, MIT, Go) is a single static executable for Linux/macOS/Windows with no interpreter or dependency install; a $4-5/mo VPS runs it as-is (RamNode publishes a MediaMTX-on-VPS guide at that price point), and it dockerizes to one container.
2. **WHIP and WHEP are first-class.** Publish from any WHIP client at `http://<host>:8889/<path>/whip` and read at `http://<host>:8889/<path>/whep` — no web page required, which means our browser encoder, recent OBS Studio versions (native WHIP output), FFmpeg, and GStreamer can all ingest through the same standardized door (RFC 9725 on the client side).
3. **Protocol matrix both directions.** Ingest via Media-over-QUIC, SRT, WebRTC, RTSP, RTMP, MPEG-TS, RTP; read via the same set plus HLS; streams are converted from protocol to protocol automatically (a browser publishing WHIP can be watched as HLS, pulled as RTSP by an on-prem recorder, and so on).
4. **Codec coverage is deliberately wide.** WebRTC legs accept AV1, VP9, VP8, H.264, H.265 video, Opus/G.722/G.711 audio, and even KLV metadata tracks — the docs warn (correctly) that browser support varies per codec, but the server side does not gate you.
5. **Ops surface is complete for a small platform.** Record streams to disk as fMP4 or MPEG-TS with playback-on-demand, a Control (REST) API, Prometheus metrics, an HTTP/JWT/internal authentication stack, event webhooks, hot config reload, and built-in pprof-compatible CPU/RAM performance monitoring — enough to run 100-creator operations without a second control plane.

## The GPU-less CPU cost reality

1. **MediaMTX remuxes; it never transcodes.** Protocol conversion is container-level repackaging (e.g., WebRTC's RTP packets into fMP4 HLS segments); on a GPU-less VPS, routing a few 1080p streams costs single-digit CPU percent because no pixel is re-encoded. This is why MediaMTX itself is famously light.
2. **The moment you need transcoding, you need ffmpeg — and CPU.** MediaMTX's own docs route re-encoding through an external FFmpeg/GStreamer sidecar, typically a `runOnAvailable` hook that republishes a re-encoded variant of the stream (their example: `ffmpeg ... -c:v libx264 -preset ultrafast -b:v 600k` into a `/compressed` path). That `ultrafast` preset in the official example is not laziness; it is the acknowledgement that software x264 at real-time needs every shortcut it can get.
3. **The ladder multiplies the bill linearly.** Each additional bitrate rung is another software encode. Rough reality on a typical 2-4 vCPU VPS: one 1080p `veryfast` x264 rung can consume a core or more, so a 3-rung ladder for one creator can saturate the box — you size the VPS for `rungs x creators x cores-per-rung`, not for `creators`.
4. **Software-encode quality/perf degrades together.** Pushing `ultrafast`/`superfast` to keep real-time raises bitrate for the same quality (worse compression) and still risks falling below source fps on bursts; the classic escape hatches are Intel QuickSync iGPUs (a used desktop with a UHD 630 is a budget transcode box), NVENC on any modern NVIDIA card, or VAAPI — none of which exist on a $4 VPS.
5. **The H.265-for-viewers trap.** Serving H.265 over WebRTC works server-side but the client matrix is hostile — MediaMTX's own WebRTC docs note many browsers can't read H.265 over WebRTC and Chrome supports it only on Windows with a capable GPU, recommending fallback re-encode to H.264 baseline + Opus via FFmpeg. So "self-host to get H.265" usually still means transcoding at the edge of the browser fleet, and H.264 streams with B-frames are unreadable by browsers over WebRTC outright.

## When the VPS beats the edge

1. **Full control of the media plane.** Your own ICE/TURN topology, your own session limits, your own recording retention — no per-minute pricing, no provider feature gates, no migration risk when a vendor re-platforms (as Cloudflare did moving Stream Live WHIP/WHEP onto Realtime in March 2025).
2. **Codec sovereignty.** H.265 ingest from IP cameras, AV1 relaying, KLV drone telemetry, SRT contribution from field gear: MediaMTX accepts all of it today, while edge WHIP surfaces are bounded by what the provider's WebRTC stack supports.
3. **Predictable flat cost at moderate, known scale.** A $20-40/mo box serving a few hundred concurrent HLS viewers (with caching/CDN in front of the HLS output) can undercut usage-based edge pricing, and there is no per-GB surprise if you peer it behind a cheap unmetered host.
4. **Data residency and privacy constraints.** Media stays on hardware you control in a jurisdiction you choose — useful for compliance-driven customers the edge terms can't satisfy.
5. **Escape hatch that composes, not replaces.** Because ingest is WHIP and egress is HLS, you can run MediaMTX for one cohort (say, high-bitrate H.265 camera feeds) while the browser-encoder Cloudflare path serves the long tail — the client contract (WHIP in, HLS out) is identical on both.

## When the VPS loses

1. **Bandwidth and fan-out.** One VPS NIC serving raw HLS to thousands of viewers is a single point of congestion; the edge's entire value is anycast fan-out and DDoS absorption. Past a few hundred concurrent viewers you are re-inventing a CDN behind a box with one uplink.
2. **Ops burden is real and permanent.** Certificates, TURN when viewers sit behind symmetric NATs, disk-full recording volumes, DDoS, kernel upgrades, 3 AM stream-down pages — the edge path deletes this entire category, and the performance-monitor/pprof tooling only helps once someone is paged.
3. **No elasticity.** A surprise viral stream on a fixed VPS falls over (CPU for ladders, NIC for viewers); the same stream on the edge just bills more.
4. **Total cost crosses over quickly with scale.** $4/mo is the entry price, not the price: real deployments need the transcode cores (`rungs x creators`), TURN bandwidth (relayed viewers pay double through the box), and spare capacity for peaks — while the Cloudflare BYO-HLS path's cost floor is R2 ops + storage with free viewer egress.
5. **You own WebRTC debugging.** ICE failures across corporate NATs, UDP blocking, and codec negotiation bugs become your tickets; MediaMTX's docs themselves walk a ladder of ICE mitigations (static UDP/TCP ports, STUN hole-punching, TURN over TCP with Coturn) that you must operate.

## Deployment shape that worked

1. **Front door.** MediaMTX on a 2-4 vCPU VPS with TLS terminated in front (Caddy/nginx), WHIP endpoints auth-gated by MediaMTX's HTTP/JWT auth or proxied behind our Worker, which mints short-lived per-creator credentials exactly as in the Cloudflare shape.
2. **Transcode tier (only if needed).** A second box or reserved cores running the ffmpeg sidecar ladders (`runOnAvailable` republish pattern, `-preset ultrafast`/`veryfast`, NVENC when available) publishing `/720p`, `/480p` variants; skip entirely when creators' browsers already encode the ladder (the WebCodecs path) and MediaMTX only remuxes.
3. **Delivery.** Serve MediaMTX's HLS from behind a CDN or cache (it emits standard HLS; low-latency variants available) rather than direct from the VPS; put recording on a separate volume with a retention cron.
4. **Observability.** Scrape MediaMTX's Prometheus metrics (reader/publisher counts per path) into the existing monitoring stack and alert on `readers > threshold` and CPU steal before streams degrade.

## Related

- `cloudflare/browser-webcodecs-whip-streaming.md` — the primary edge architecture this alternatives
- `cloudflare/cloudflare-calls-webrtc.md` — edge WebRTC (Calls/Realtime) reference
- `performance/ffmpeg-wasm-not-realtime.md` — why the transcode tier is native ffmpeg, never wasm
- MediaMTX repo: https://github.com/bluenviron/mediamtx
- MediaMTX WHIP publish docs: https://github.com/bluenviron/mediamtx/blob/master/docs/3-publish/05-webrtc-clients.md
- MediaMTX WHEP read docs: https://github.com/bluenviron/mediamtx/blob/master/docs/4-read/03-webrtc.md
- MediaMTX re-encoding guide: https://github.com/bluenviron/mediamtx/blob/master/docs/2-features/07-remuxing-reencoding-compression.md
- MediaMTX performance monitoring: https://mediamtx.org/docs/features/performance
- RamNode MediaMTX-on-VPS guide: https://www.ramnode.com/guides/mediamtx
