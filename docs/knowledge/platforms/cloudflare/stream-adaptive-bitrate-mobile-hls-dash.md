# stream-adaptive-bitrate-mobile-hls-dash

**Issue:** Cloudflare Stream ABR delivery differences on mobile vs
desktop — HLS/DASH protocol selection, LL-HLS support, autoplay
rules, signed-URL timing, Stream Player vs HLS.js.
**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Video works on desktop but stalls or shows blank on iOS in-app
browsers. Autoplay fires audio on Android and gets blocked.
Signed tokens expire before first segment loads on 3G. HLS.js
throws silently on iOS.

## Context

Stream publishes every upload as HLS (`.m3u8`) and DASH (`.mpd`)
with a 240p–1080p ladder. Which protocol the device can consume is
platform-constrained. example project: portrait short clips, scroll-
autoplay, anonymous signed access — all traffic-weighted mobile.

## HLS vs DASH support matrix

DASH requires Media Source Extensions (MSE). iOS Safari and all
iOS in-app browsers (WKWebView, Chrome for iOS, Firefox for iOS)
never expose MSE — DASH and HLS.js are unavailable on any iOS
context with no exception.

```
Platform                 | HLS native | DASH/MSE | HLS.js
-------------------------|------------|----------|-------
iOS Safari (≥ 14)        | YES        | NO *1    | NO *2
iOS in-app (WKWebView)   | YES        | NO       | NO *2
iPadOS Safari            | YES        | NO *1    | NO *2
Android Chrome (≥ 80)    | NO native  | YES      | YES
Android Firefox          | NO native  | YES      | YES
Desktop Chrome/Edge/FF   | NO native  | YES      | YES
Desktop Safari (macOS)   | YES        | partial  | NO *2
```

*1 iOS 17.1+ added experimental MSE; not production-ready for
   DASH at scale.
*2 HLS.js depends on MSE. On iOS, only a native `<video>` pointing
   at the `.m3u8` URL works. Serving DASH to iOS renders nothing.

The Stream Player iframe selects the protocol automatically. A
custom player must branch on platform before choosing a manifest.

## Low-latency HLS (LL-HLS) mobile status

LL-HLS (Apple's own extension — partial segments, blocking
playlist reload) cuts live latency to ~2–3 s. 2026 support:

```
Context                  | LL-HLS
-------------------------|-------------------------------------
iOS Safari (≥ 14)        | YES — native
macOS Safari (≥ 14)      | YES — native
Android + hls.js ≥ 1.2   | YES — MSE path
Stream built-in player   | YES — auto-detects per platform
Custom HLS.js embed      | Set preferLowLatency: true in conf
```

Enable on a live input: `{ "preferLowLatency": true }`. Applies
to live inputs only — VOD feeds gain nothing and partial-segment
requests can break HTTP/1.1 caches. example project's VOD clip feed
should leave LL-HLS off.

## Thumbnail and poster frame delivery

Stream thumbnails are generated on-demand from the CDN edge:

```
https://videodelivery.net/<uid>/thumbnails/thumbnail.jpg
  ?time=2s     # default 0s
  &height=480  # resize maintaining AR
  &width=270   # portrait: swap h/w
  &fit=crop    # crop|clip|scale|fill
```

Set `poster` on the Stream embed:
```html
<stream

  poster="https://videodelivery.net/<uid>/thumbnails/thumbnail.jpg
          ?time=2s&height=480&width=270"
  muted autoplay playsinline controls
></stream>
```

For signed videos the poster URL needs its own short-lived token
(60 s is enough — single CDN hit). Do not reuse the playback JWT;
differing expiry windows cause a 401 to the `<img>` on slow mobile.

## Mobile bandwidth and initial quality rung

Stream ABR measures TTFB on the manifest and adjusts per segment.
Cold 4G typically lands on 360p–480p and steps up within 2–3
segments (~6 s). Do not force an initial quality level on mobile;
forcing 1080p on congestion causes a rebuffer worse than a brief
low-quality start. Portrait clips at 720 × 1280 cost ~1.5 Mbps;
480 × 854 at ~700 kbps is the practical example project quality floor.
Custom HLS.js: use `hls.startLevel = -1` (auto).

## Autoplay policy on mobile

All major mobile browsers block unmuted autoplay by 2026.

```
Autoplay succeeds                 | Autoplay blocked
----------------------------------|------------------------
muted video, any source           | unmuted, first load
muted video + prior user gesture  | unmuted, no prior tap
video played earlier in tab       | unmuted inside iframe
                                  | without allow=autoplay
```

Stream **iframe** embed (append `?muted=true&autoplay=true`):
```html
<iframe
  src="https://customer-<code>.cloudflarestream.com/<uid>/iframe
       ?muted=true&autoplay=true"
  allow="autoplay; encrypted-media; fullscreen; picture-in-picture"
  loading="lazy"></iframe>
```

Stream **web component** (handles iOS internally):
```html
<stream  muted autoplay playsinline controls></stream>
```

`playsinline` prevents iOS from opening the full-screen system
player on play, breaking scroll-feed UX. The Stream iframe sets
it internally; a raw `<video>` or web component must set it on
the element itself, not on a wrapper div.

## Signed URLs and token expiry on slow mobile

Default token TTL is 3600 s. Failure modes on slow mobile:
1. Token minted at scroll → user pauses 70 min → 401 on resume.
2. 60 s token minted server-side → slow API propagation → stale
   before first segment.

Recommended TTLs:

```
Use case                  | Recommended exp
--------------------------|-----------------------------------
Thumbnail <img>           | now + 60 s
Manifest fetch (VOD)      | now + 300 s minimum
Playback session mobile   | now + 3600–14400 s (1–4 h)
Live stream session       | now + (expected duration + 1800 s)
```

Sign the manifest URL only — Stream does not re-validate per
segment. Token expiry fires at the next manifest reload.

```ts
const { result: { token } } = await (await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${accountId}`
  + `/stream/${uid}/token`,
  {
    method: 'POST',
    headers: { Authorization: `Bearer ${env.STREAM_API_TOKEN}` },
    body: JSON.stringify({ exp: Math.floor(Date.now()/1000) + 14400 }),
  }
)).json();
// <stream  token={token}> or ?token=<token> on iframe
```

Cache minted tokens in KV (TTL = exp) and re-issue at feed
refresh, not on each card render.

## Stream Player vs HLS.js on mobile

```
Factor              | Stream Player iframe   | Custom HLS.js
--------------------|------------------------|------------------
iOS support         | YES (native HLS)       | NO (no MSE)
Android support     | YES                    | YES
CPU/battery         | Separate process,      | Main-thread transmux
                    | hardware decode        | (enable Worker!)
fMP4/CMAF           | YES default            | YES — less CPU than
                    |                        | TS transmux
Feed integration    | Hard (iframe boundary) | Full JS access
Custom controls     | Via postMessage API    | Direct DOM
Portrait 2026       | YES auto               | CSS required
Signed tokens       | token= on src param    | Query on .m3u8
```

- **Stream Player:** simplest iOS-safe path; iframe runs in a
  separate process so HW decode does not compete with scroll.
- **HLS.js (Android only):** set `enableWorker: true`; prefer
  DASH (fMP4) to avoid TS transmux CPU overhead.
- **Gate on MSE:** `if (!Hls.isSupported()) { /* native video */ }`

## Anti-patterns

1. **Serving DASH manifest URL to iOS.** Silently renders nothing.
2. **`autoplay` without `muted` on mobile.** Blocked; no error
   fires, the video just never starts.
3. **Omitting `playsinline` on iOS.** System player hijacks UX
   and breaks scroll-feed autoplay.
4. **60 s signed tokens for mobile playback sessions.** Expires
   mid-session on slow networks. Use 1–4 h.
5. **Reusing the playback token for thumbnail `<img>`.** Differing
   expiry windows serve a 401 to the image element.
6. **HLS.js on all platforms.** No MSE on iOS = runtime throw
   in the playback critical path.

## Gotchas

- **WKWebView is not a custom engine.** Chrome/Firefox for iOS
  use WKWebView; MSE restrictions are identical to Safari.
- **LL-HLS requires HTTP/2.** A proxy stripping H2 silently
  degrades to standard HLS latency. Check:
  `curl -I --http2 <manifest-url>`.
- **Token expiry fires at manifest reload, not per segment.**
  Viewers finish the current window even after JWT exp; live
  streams reload every few seconds, VOD on seek.
- **`enableWorker` may default off.** Without it, TS transmux
  blocks the main thread and causes scroll jank on low-end Android.

## Verification

- Real iPhone, Safari throttled "Fast 3G": video starts within
  4 s, no autoplay-block console errors, no system AVPlayer.
- Same URL in iOS WKWebView harness: HLS plays; DASH manifest not
  served.
- Android Chrome, DevTools → Media panel: confirm stream type;
  CPU % < 15 % during scroll with HLS.js Worker enabled.
- Mint token `exp = now + 90`, wait 95 s, fetch manifest → 401.
- Stream iframe without `muted=true` on iOS → autoplay blocked.

## Related

- `cloudflare/stream-best-practices.md`
- `cloudflare/r2-streaming-hls-pipeline.md`
- `cloudflare/browser-webcodecs-whip-streaming.md`
- `cloudflare/cloudflare-calls-webrtc.md`
- `cloudflare/r2-signed-urls.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/stream/viewing-videos/using-own-player/
- https://developers.cloudflare.com/stream/viewing-videos/securing-your-stream/
- https://developers.cloudflare.com/stream/viewing-videos/displaying-thumbnails/
- https://developers.cloudflare.com/stream/viewing-videos/using-the-stream-player/using-the-player-api/
- https://blog.cloudflare.com/cloudflare-stream-low-latency-hls-open-beta/
- https://developer.apple.com/documentation/http-live-streaming/enabling-low-latency-http-live-streaming-hls
- https://caniuse.com/mpeg-dash
- https://community.cloudflare.com/t/timed-token-works-even-after-expiration/472003
