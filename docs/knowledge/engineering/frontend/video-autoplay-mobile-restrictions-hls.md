# Video Autoplay and Inline Playback Restrictions — Mobile

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Desktop Chrome plays example project video posts the moment they scroll into
view, but on an iPhone the same feed is a wall of frozen thumbnails.
Users tap individual posts expecting inline playback and the video
hijacks the screen into the native fullscreen player. Unmuted videos
that work fine in Chrome DevTools mobile emulation refuse to start
on a real device. Adding `autoplay` fixes Android but not iOS. A
video that autoplays correctly on iOS 17 silently fails on iOS 18
in Low Power Mode. The `play()` call throws an unhandled Promise
rejection that surfaces in crash reporting and breaks React state.

## Context

Mobile browsers enforce autoplay policies stricter than desktop.
The fundamental rule: muted video with the correct attribute
combination is the only universally reliable autoplay path on
mobile. Unmuted autoplay requires an explicit user gesture on every
major mobile browser and cannot be used for scroll-driven feeds.
iOS Safari adds a second constraint — `playsinline` must be present
or the `<video>` element opens the native fullscreen player,
breaking TikTok-style inline feed layout. example project's scroll-driven feed
must therefore use `muted + playsinline + autoplay` on every
`<video>`, manage play/pause through Intersection Observer, and
handle `play()` Promise rejection gracefully for Low Power Mode and
permission-denied cases. Cloudflare Stream serves HLS manifests
(`.m3u8`) that iOS Safari plays natively; Android Chrome requires
hls.js via the MSE (MediaSource Extensions) API.

## Browser autoplay policies

```
Browser             Muted autoplay    Unmuted autoplay
──────────────────────────────────────────────────────────────────
iOS Safari          YES — requires    NO: always blocked;
(all versions)      playsinline       user gesture required
Safari macOS        YES               MEI threshold or prior
                                      user interaction on domain
Chrome Android      YES               NO on mobile — MEI does
                                      not apply; PWA / home-
                                      screen add required
Chrome Desktop      YES               MEI threshold (visits-to-
                                      playback ratio > cutoff)
Firefox Mobile      YES               NO: user gesture required
Firefox Desktop     YES               User interaction required

MEI (Media Engagement Index): Chrome per-origin score based on
ratio of visits to significant media events — audio present,
>7s played, tab active, video ≥200×140 px. Applies on desktop
only. MEI does NOT unlock unmuted autoplay on Android Chrome
regardless of how high the score is.

Conclusion for example project: all scroll-driven feed videos must be muted.
Unmuted audio requires the user to tap — reveal a volume icon
after the first play() succeeds.
```

## Required attribute combination

```html
<!-- Minimum required on every feed video — works on all browsers -->
<video
  autoplay
  muted
  playsinline
  loop
  preload="metadata"
  poster="/thumb/{videoId}.jpg"
>
  <!-- Src set in JS — see HLS section below -->
</video>
```

```
Attribute        Why it matters
──────────────────────────────────────────────────────────────
autoplay         Signals intent; browser may still block it —
                 always also call video.play() in JS and
                 handle the returned Promise
muted            Required for autoplay on all mobile browsers;
                 without it, play() rejects immediately
playsinline      iOS only: without this the <video> element
                 opens in the native fullscreen player, breaking
                 inline feed layout. Previously webkit-playsinline
                 (iOS < 10) — use both to support iOS 9
loop             Re-plays silently for feed cards; user taps
                 to open full player with audio controls
preload          "metadata" loads duration + dimensions without
                 buffering segments; "auto" is too aggressive
                 (buffers full video per card on load)
poster           Shows a frame while video loads; iOS does not
                 display the first video frame by default
```

## HLS vs native video — mobile format support

```
Format        iOS Safari          Android Chrome      Notes
──────────────────────────────────────────────────────────────────
HLS (.m3u8)   Native <video>      hls.js required     ABR built in;
              src attribute        (via MSE API)        iOS native path
DASH (.mpd)   NOT supported        dash.js via MSE     No iOS support
              natively                                  whatsoever
MP4 (H.264)   Supported           Supported            Single rendition,
              natively             natively             no ABR
MP4 (HEVC)    iOS 11+ hardware    NOT supported        Decode-only on
              decode              in Chrome            iOS hardware
WebM/VP9      NOT supported       Supported            Not viable for
              natively                                  cross-platform

Recommended strategy for example project:
  1. Always serve HLS (.m3u8) as the primary source
  2. Detect native HLS support via canPlayType before hls.js
  3. Use hls.js on non-native browsers (Android Chrome, Firefox)
  4. Never initialise hls.js on iOS — MSE is unavailable there
```

## Cloudflare Stream HLS delivery

```javascript
// Cloudflare Stream manifest URLs (never cache or proxy these)
// HLS : https://customer-<CODE>.cloudflarestream.com/<UID>/manifest/video.m3u8
// DASH: https://customer-<CODE>.cloudflarestream.com/<UID>/manifest/video.mpd
//
// Stream auto-encodes to 360p, 480p, 720p, 1080p renditions.
// ABR logic in the player/browser selects rendition by bandwidth.

import Hls from 'hls.js';

function attachHls(videoEl, hlsUrl) {
  if (videoEl.canPlayType('application/vnd.apple.mpegurl')) {
    // iOS Safari — native HLS, just set src directly
    videoEl.src = hlsUrl;
    return null;
  }

  if (Hls.isSupported()) {
    // Android Chrome, Firefox, Desktop Chrome
    const hls = new Hls({
      startLevel: -1,         // let ABR pick the first rendition
      maxBufferLength: 10,    // keep buffer small for feed scrolling
      maxMaxBufferLength: 30,
    });
    hls.loadSource(hlsUrl);
    hls.attachMedia(videoEl);
    return hls; // store ref — call hls.destroy() on unmount
  }

  // Browser cannot play HLS at all — show fallback UI
  return null;
}

// React cleanup pattern
useEffect(() => {
  const hls = attachHls(videoRef.current, streamUrl);
  return () => hls?.destroy();
}, [streamUrl]);
```

## Handling play() rejection and Low Power Mode

```javascript
// video.play() is async and CAN reject — always await and catch
async function safePlay(videoEl) {
  try {
    await videoEl.play();
  } catch (err) {
    if (err.name === 'NotAllowedError') {
      // Autoplay blocked: Low Power Mode, permissions policy, or
      // unmuted video attempted. Show a tap-to-play overlay.
      showPlayOverlay(videoEl);
    } else if (err.name === 'NotSupportedError') {
      // Codec or source not supported on this device
      showUnsupportedFallback(videoEl);
    }
    // AbortError: play() interrupted by pause() or src change —
    // normal in a fast-scrolling feed, safe to ignore.
  }
}

// iOS Low Power Mode behaviour:
//   • Autoplay blocked even with muted + playsinline
//   • play() rejects with NotAllowedError
//   • Frame rate and quality reduced during any playback
//   • No JS API to detect Low Power Mode; only signal is the
//     NotAllowedError rejection — degrade gracefully, do not retry
```

## Intersection Observer for scroll-driven autoplay

```javascript
// Play video when ≥50% visible in viewport; pause on scroll-out.
// Consistent cross-browser — iOS Safari auto-pauses natively but
// Intersection Observer gives explicit control and correct timing.

const THRESHOLD = 0.5;

function createFeedObserver() {
  return new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        const video = entry.target.querySelector('video');
        if (!video) return;
        if (entry.intersectionRatio >= THRESHOLD) {
          safePlay(video);
        } else {
          video.pause();
        }
      });
    },
    { threshold: [0, THRESHOLD, 1.0] }
  );
}

const observer = createFeedObserver();
feedCardEls.forEach((card) => observer.observe(card));

// Cleanup
observer.disconnect();
```

## Anti-patterns

- **`autoplay` without `muted`** — browsers ignore the `autoplay`
  attribute for unmuted video on mobile. The video silently freezes;
  there is no console error to indicate why.
- **Omitting `playsinline` on iOS** — the `<video>` element opens
  the native fullscreen player. No warning; UX simply diverges from
  the design. This is the single most common iOS-specific bug.
- **Not handling the `play()` Promise** — `video.play()` is async
  and rejects on block. Unhandled rejections appear in crash reports
  and can corrupt React component state.
- **Caching Cloudflare Stream manifests** — `.m3u8` manifests are
  dynamic; proxying or caching them breaks ABR rendition selection
  and produces stale segment URLs causing playback errors.
- **`preload="auto"` on feed items** — each card eagerly buffers
  30–60 s of video, consuming mobile data and battery on load. Use
  `preload="metadata"` for feed items.
- **Initialising hls.js on iOS** — iOS Safari does not expose MSE
  in the standard way; hls.js will error silently. Always branch on
  `canPlayType` before calling `Hls.isSupported()`.

## Gotchas

- **Low Power Mode has no JS detection API** — there is no
  `navigator.lowPowerMode`. The only signal is `play()` rejecting
  with `NotAllowedError`. Show a tap-to-play indicator; do not
  retry in a loop.
- **`webkit-playsinline` is only needed for iOS 9** — iOS 10+
  honours the un-prefixed `playsinline`. Including both is
  harmless; dropping the prefixed version is safe for modern
  targets.
- **iOS hides native controls in inline mode** — when `playsinline`
  is set, iOS renders a minimal control bar that differs visually
  from Android/desktop. Build custom controls for a consistent
  Reels-style UI across platforms.
- **hls.js must be destroyed on unmount** — `hls.destroy()` releases
  the MSE `MediaSource` and removes event listeners. Leaking
  instances causes memory growth in long-running feeds.
- **MEI does not help on Android Chrome** — even users who have
  watched hours of video on the origin cannot get unmuted autoplay
  on mobile Chrome. Do not design features that depend on it.
- **Cloudflare Stream `clientBandwidthHint` override** — the query
  parameter bypasses ABR; only use it if you have a reliable
  out-of-band bandwidth measurement. Wrong values degrade quality
  on constrained connections.

## Verification

- Every feed `<video>` element has `autoplay muted playsinline loop`
  attributes present in the HTML.
- All `video.play()` calls are awaited; `NotAllowedError` is caught
  and shows a visible tap-to-play overlay.
- HLS source attached via native `src` on iOS, hls.js on other
  browsers; `canPlayType` gates the branch before `Hls.isSupported()`.
- Intersection Observer pauses cards that scroll off-screen; only
  the in-view card plays (muted, but pausing saves battery and data).
- hls.js instances are destroyed in `useEffect` cleanup functions.
- Cloudflare Stream `.m3u8` manifests are fetched directly from
  Stream's CDN — not proxied or cached by example project's infrastructure.
- Manually tested on a real iPhone (not DevTools emulation) in both
  normal mode and Low Power Mode.

## Related

- `documentation/docs/policies/mobile/mobile-video-playback-media3-avplayer.md`
- `documentation/docs/policies/cloudflare/stream-best-practices.md`
- `documentation/docs/policies/cloudflare/r2-streaming-hls-pipeline.md`

## Source URLs (verified 2026-08-17)

- Autoplay policy in Chrome — https://developer.chrome.com/blog/autoplay
- New <video> Policies for iOS (WebKit) — https://webkit.org/blog/6784/new-video-policies-for-ios/
- Cloudflare Stream: Use your own player — https://developers.cloudflare.com/stream/viewing-videos/using-own-player/
- What is HTTP Live Streaming — https://www.cloudflare.com/learning/video/what-is-http-live-streaming/
- HLS.js developer guide — https://www.videosdk.live/developer-hub/hls/hls-js
