# mobile-video-playback-media3-avplayer

**Issue:** Video is table stakes in feeds, onboarding, and social features, and users abandon a video that stalls for more than a second or two. The Android media stack has churned heavily — standalone ExoPlayer was folded into the Media3 library, MediaPlayer is effectively legacy, and Google shipped new preloading APIs in September 2025 — while iOS AVPlayer is stable but has its own buffering and variant-switching rules that surprise newcomers. Hybrid apps add a third stack: HTML5 video inside a WebView/Capacitor shell behaves differently around autoplay, fullscreen, battery, and Picture-in-Picture. This article covers stack selection, startup latency engineering, lifecycle and memory discipline, and error handling for production playback.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Stack Selection

1. **Media3 (ExoPlayer) on Android.** Use the Media3 media3-exoplayer artifacts; the old standalone ExoPlayer namespace is frozen. Media3 also brings MediaSession, Transformer for editing, and UI components under one versioned umbrella, which ends the dependency-combination bugs of the ExoPlayer 2.x era.

2. **AVPlayer on iOS.** AVPlayer with AVPlayerLayer remains the default; AVQueuePlayer for gaps-free sequences, AVPlayerLooper for looping ambient video. For feed-style inline video on iOS 16+, prefer AVPlayerViewController configured for inline playback over hand-rolled controls unless you need deep customization.

3. **WebView video is a third platform.** In a Capacitor shell, HTML5 video routes through the system media stack with WebView-specific autoplay policies (muted + playsinline required for autoplay), inconsistent PiP, and no direct access to buffering controls. For anything beyond short clips, bridge to a native player via a plugin rather than fighting the WebView.

4. **Codec and format matrix.** Device codec support varies wildly on Android; consult MediaCodecList at runtime for HEVC/AV1/ HDR support rather than assuming. Serve HLS with a broad variant ladder on Android and let the track selector adapt; iOS hardware handles HLS natively with fMP4/CMAF.

## Startup Latency

1. **Preload with Media3 PreloadingManager.** The preloading APIs introduced in the Media3 September 2025 release (PreloadingManager, preloading media source factories) fetch and buffer the first segments before playback starts. The documented sliding-window pattern — preload the next N feed items as the user scrolls — is the reference implementation for feed-style apps.

2. **Tune LoadControl deliberately.** Defaults buffer tens of seconds, which delays first frame and wastes memory in feeds. Set min/max buffer ms and buffer-for-playback ms per surface: aggressive small buffers for short inline clips, larger buffers for long-form casting.

3. **Start low, step up.** Begin playback on a conservative variant (480p) and let ABR step up once the buffer is established. Starting at the top variant produces the classic black-frame-then-stall experience users rate one star.

4. **Measure time-to-first-frame, not play().** Instrument from user intent (scroll stop, tap) to first rendered frame. Reddit's engineering team attributes most perceived playback wins to startup work, not average bitrate — the same lesson applies to any feed product.

## Lifecycle and Resource Management

1. **Release when not visible.** ExoPlayer instances hold decoder instances, sockets, and buffers; keep players only for visible surfaces. The official guidance is to initialize when becoming visible and release when not — pool or recreate rather than keeping off-screen players paused.

2. **One player per feed viewport.** Use a player pool sized to the visible viewport plus one preload slot. Attaching a player to every recycled list item is the standard memory-leak path in Compose/RecyclerView video feeds.

3. **Audio focus and ducking.** Request audio focus on play, abandon on pause/release, and respond to transient loss by ducking. Ignoring focus gets your app killed by media-key routing and flagged in quality review.

4. **Background and PiP rules.** Decide explicitly whether playback continues in background (needs a media session and, for Android, a foreground-service media type) or hands off to PiP. Android 14+ enforces stricter foreground-service media types; declare mediaPlayback in the manifest and handle the PiP state changes (onPictureInPictureModeChanged) to swap UI chrome.

5. **Compose integration lifetime.** With Media3 in Compose, tie the player to remember with DisposableEffect keyed on lifecycle, not to composition alone, or config changes and navigation will leak decoders.

## Error Handling and Adaptive Streaming

1. **Categorize errors before retrying.** ExoPlayer PlaybackException carries ERROR_CODE_BEHIND_LIVE_WINDOW, timeout, network, and decoder classes. Retry behind-live-window by resetting position, retry network with backoff, and never auto-retry decoder init failures — escalate to software fallback or an error state.

2. **Track selection parameters as product surface.** TrackSelectionParameters let you cap resolution on cellular, force captions, or prefer languages — set them from user settings rather than shipping ABR defaults as the only behavior, and expose a data-saver toggle.

3. **DRM and offline.** Widevine (Android) and FairPlay (iOS) via MediaDrm/AVContentKeySession for protected streams; budget key-fetch latency into startup time. For offline, download with DownloadManager in Media3 and validate license expiry on playback, not just on download.

4. **Instrument the playback funnel.** Emit events for intent, first frame, rebuffer count and duration, error code, and exit reason, and segment by network type, device tier, and CDN. Aggregate into crash-free-style dashboards — playback success rate deserves the same SLO treatment as crash rate (see the crash-free-rate SLO article in this knowledge base).
