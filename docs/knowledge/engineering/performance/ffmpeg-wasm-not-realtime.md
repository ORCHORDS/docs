# ffmpeg-wasm-not-realtime

**Issue:** While designing the browser-encoder streaming pipeline (see `cloudflare/browser-webcodecs-whip-streaming.md`) we evaluated FFmpeg.wasm as the in-browser transcode stage — the idea being "just run our existing ffmpeg recipes in the tab." The verified finding: FFmpeg.wasm is not suitable for real-time transcoding. The default core is single-threaded wasm, the multithreaded core requires SharedArrayBuffer which requires cross-origin isolation (COOP/COEP) that many hosting setups can't or won't ship, wasm has no path to FFmpeg's SIMD and hardware-codec acceleration, and measured throughput lands 2x (best case, SIMD-friendly workloads) to 10-50x (typical transcoding, worst on H.265/VP9) slower than native ffmpeg on the same machine. This article records the evidence, the root causes, where FFmpeg.wasm is nonetheless the right tool, and what to use when the work is real-time.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The finding, with numbers

1. **The maintainers say it outright.** The official FFmpeg.wasm performance docs state it will not match native FFmpeg even in the multithreaded version, with their own benchmark averaging ~5.2s for a job native completes in a fraction of that (ffmpegwasm.netlify.app/docs/performance).
2. **Field reports range 2x to 50x slower.** A Show HN author measured ~2x slower than native for their transcoder (best case, with the SIMD-enabled build on friendly codecs); the renderio.dev FFmpeg.wasm guide measures native FFmpeg as easily 10-50x faster depending on codec, with H.265 and VP9 the worst offenders.
3. **Academic baseline agrees on the multiplier floor.** Janson et al.'s WebAssembly-vs-native study puts generic compute-heavy wasm at ~1.55x slower in Chrome and ~1.45x in Firefox versus native — and FFmpeg's problem is that its *fast paths* (SIMD, hardware codecs, threads) are exactly what wasm lacks, so real workloads slide toward the pessimistic end of the range.
4. **What this means for a live pipeline.** Real-time means sustaining `encode_fps >= source_fps` continuously with headroom; a 1080p30 H.264 transcode that runs at 3-8 fps in the tab is a slideshow, not a stream. There is no tuning flag that closes a 10x gap.

## Root causes (why it is slow)

1. **The default core is single-threaded.** `@ffmpeg.wasm/core` ships without threads; one core does demux, decode, scale, filter, encode, mux. The multithreaded core exists (`core-mt`) but only browsers with SharedArrayBuffer can run it, and the maintainers' own "next steps" discussion (ffmpeg.wasm#415) documents the compatibility problems that have kept threading non-default.
2. **SharedArrayBuffer drags in COOP/COEP.** Threads share memory via SharedArrayBuffer, which browsers only expose to cross-origin-isolated pages — `Cross-Origin-Opener-Policy: same-origin` plus `Cross-Origin-Embedder-Policy: require-corp` on every document and every embedded third-party resource (ffmpeg.wasm#137 documents the request; the dev.to FFmpeg-in-browser writeup shows the deployment pain). Any page embedding third-party iframes/scripts without CORP headers breaks under `require-corp`.
3. **No SIMD parity with native FFmpeg.** Native FFmpeg gets much of its speed from hand-tuned SIMD intrinsics per architecture; wasm SIMD is a subset, compiled FFmpeg does not transparently recover its native fast paths, and the maintainer discussion calls proper SIMD intrinsics "not easy but key to success" — i.e., still the future path, not the shipped one.
4. **No hardware codecs.** Native ffmpeg uses VAAPI/NVENC/VideoToolbox/QuickSync; wasm cannot reach any of them, so every pixel goes through software encode. The "Pure Rust FFmpeg vs Reality" analysis makes the general point: FFmpeg-class performance is mostly SIMD + hardware acceleration, which is precisely what the sandbox withholds.
5. **A 2 GB memory ceiling.** wasm32 addressing caps the linear memory, so the in-memory filesystem (where input and output blobs live) hard-fails on large media — long transcodes and 4K sources hit the wall regardless of speed.

## Where FFmpeg.wasm IS the right tool

1. **Batch and offline jobs.** Clip export, format conversion of short files, subtitle burn-in for a 30-minute upload — jobs where "takes 30s instead of 3s" is acceptable because the user is waiting on a progress bar, not watching live.
2. **Client-side trim and cut operations.** Cutting keyframe-aligned segments with stream copy (`-c copy`) avoids re-encoding entirely and is dominated by I/O, not compute — this runs fine and keeps the media off your servers.
3. **Thumbnails, waveforms, metadata, probes.** `ffprobe`-style inspection, poster-frame extraction, and audio peak scanning are light, bursty, and perfect for moving off the server: the dev.to case study of replacing server transcoding with browser-side FFmpeg.wasm documents real cost savings for exactly this class of work.
4. **Privacy-sensitive or air-gapped processing.** When policy (not performance) requires media never to leave the device, slow is a feature; pair it with progress UI and file-size guards under the 2 GB ceiling.
5. **Cost offload at small scale.** If you'd otherwise spin a $40/mo worker to do occasional one-off transcodes, a 10x slowdown executed on the user's own CPU is a legitimate trade — up to the point users complain about fan noise and battery.

## What to use instead for real-time work

1. **WebCodecs for anything live in a browser.** WebCodecs reaches the platform's actual hardware encoders (AV1/VP9/H.264 + Opus), which is why the Transloadit real-time-filters work and every serious in-tab encoder landed on it; this is the encoding stage of our streaming pipeline (see `cloudflare/browser-webcodecs-whip-streaming.md`).
2. **Mux only what you must.** For packaging encoded chunks as HLS/CMAF you do not need ffmpeg at all — WebCodecs emits exactly the encoded chunks + timestamps a JS muxer needs, and a Worker can segment without a heavyweight dependency.
3. **Native ffmpeg on a server or VPS when server-side transcode is unavoidable.** Re-encoding rungs, format normalization, or DVR turnaround belong on native ffmpeg (with `libx264 -preset veryfast/ultrafast` at minimum, NVENC/VAAPI if available), not in the browser; see `cloudflare/mediamtx-vps-alternative.md` for the self-hosted media-server shape where this lives.
4. **Set the acceptance bar before benchmarking alternatives.** Real-time = sustained source-fps with <1.0 average `encodeQueueDepth` (WebCodecs) or `speed > 1x` (ffmpeg `-progress` speed field) for the duration of a stream, measured on your worst supported device, not your dev laptop.

## Gotchas

1. **The "it works on my machine" trap.** Without COOP/COEP deployed end-to-end, `core-mt` throws `SharedArrayBuffer is not defined` at runtime — test the headers in production, including on pages you don't fully control.
2. **The 2 GB OOM mid-job.** Long inputs fail late, after minutes of work; chunk or pre-trim before feeding the wasm filesystem, and surface the failure honestly rather than retry-looping.
3. **The demo-to-production gap.** FFmpeg.wasm demos transcode 5-second clips; extrapolating that to a 2-hour stream multiplies both time and memory linearly until the ceiling breaks it. Validate with production-length media.
4. **Don't fight the architecture.** If you find yourself writing a SharedArrayBuffer polyfill or hand-compiling pthreads builds, stop — the correct move is WebCodecs (browser) or native ffmpeg (server), and this document is the receipt.

## Related

- `cloudflare/browser-webcodecs-whip-streaming.md` — the WebCodecs-based pipeline that replaced this idea
- `cloudflare/mediamtx-vps-alternative.md` — server-side transcoding shape
- FFmpeg.wasm performance docs: https://ffmpegwasm.netlify.app/docs/performance/
- Next steps for ffmpeg.wasm (#415): https://github.com/ffmpegwasm/ffmpeg.wasm/discussions/415
- Version without SharedArrayBuffer (#137): https://github.com/ffmpegwasm/ffmpeg.wasm/issues/137
- FFmpeg.wasm guide (10-50x measurements): https://renderio.dev/blogs/ffmpeg-wasm-guide
- Show HN wasm transcoder report (~2x): https://news.ycombinator.com/item?id=24588523
- WASM vs native (arXiv): https://ar5iv.labs.arxiv.org/html/1901.09056
- Real-time with WebCodecs (Transloadit): https://transloadit.com/devtips/real-time-video-filters-in-browsers-with-ffmpeg-and-webcodecs/
