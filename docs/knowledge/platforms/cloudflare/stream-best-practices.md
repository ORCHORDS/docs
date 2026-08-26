# stream-best-practices

**Issue:** Cloudflare Stream — video upload, transcode, deliver
**Date:** 2026-08-09
**Status:** documented

## Symptom
Users upload videos. You transcode them yourself.
The CPU is heavy. The storage is large. The CDN
delivery is slow. You wish it were a managed service.

## Root cause
**Video is hard.** Use Cloudflare Stream.

**Source:** CF Stream:
https://developers.cloudflare.com/stream/

## The "Stream" concept

Cloudflare Stream:
- **Upload:** Direct or link
- **Encode:** Adaptive bitrate (240p-1080p)
- **Deliver:** HLS / DASH
- **Player:** Built-in
- **Live:** Stream Live
- **Portrait:** Native vertical support

The video is end-to-end.

## The "upload" pattern

For an upload:
```bash
curl -X POST -F file=@video.mp4 \
  https://api.cloudflare.com/client/v4/accounts/{account_id}/stream \
  -H "Authorization: Bearer {api_token}"
```

The video is uploaded.

## The "direct creator upload" pattern

For user uploads (creator pattern):
```ts
const upload = await fetch('https://api.cloudflare.com/client/v4/accounts/{account_id}/stream/direct_upload', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${env.STREAM_API_TOKEN}` },
  body: JSON.stringify({
    maxDurationSeconds: 3600,
  }),
});

const { uploadURL, uid } = await upload.json();

// The user uploads directly to uploadURL
```

The user uploads directly.

## The "supported formats" pattern

For formats:
- **Containers:** MP4, MKV, MOV, AVI, FLV, MPEG-2 TS, WebM
- **Video codecs:** H.264, H.265, VP8, VP9
- **Audio:** AAC

The formats are standard.

## The "encoding" pattern

For encoding:
- **Renditions:** 240p, 360p, 480p, 720p, 1080p
- **Adaptive bitrate:** Auto
- **Frame rate:** Up to 70 FPS
- **Portrait:** Native (new 2026)

The encoding is automatic.

## The "player" pattern

For the player:
```html
<stream  controls></stream>
```

Or via iframe:
```html
<iframe
  src="https://customer-<code>.cloudflarestream.com/<video-uid>/iframe"
  allow="autoplay; encrypted-media"
></iframe>
```

The player is built-in.

## The "CSP" pattern

For CSP, allow Stream:
```
frame-src: customer-<code>.cloudflarestream.com *.videodelivery.net
media-src: customer-<code>.cloudflarestream.com *.videodelivery.net
img-src: customer-<code>.cloudflarestream.com *.videodelivery.net
```

The CSP is set.

## The "live" pattern

For live:
```bash
# 1. Create live input
curl -X POST \
  https://api.cloudflare.com/client/v4/accounts/{account_id}/stream/live_inputs \
  -H "Authorization: Bearer {api_token}"
```

The live stream is set up.

```ts
// 2. Use the URL in OBS or your encoder
const rtmpUrl = liveInput.rtmpUrl;
const streamKey = liveInput.streamKey;
```

The encoder connects.

## The "thumbnail" pattern

For thumbnails:
```ts
// Generate a thumbnail
const thumb = await fetch(`https://videodelivery.net/<uid>/thumbnails/thumbnail.jpg?time=10s`);

// Animated thumbnail
const animated = await fetch(`https://videodelivery.net/<uid>/thumbnails/animated.gif`);
```

The thumbnail is generated.

## The "recording" pattern

For recording a live:
```ts
const recording = await fetch(`https://api.cloudflare.com/client/v4/accounts/{account_id}/stream/live_inputs/{input_id}/recordings`, {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${env.STREAM_API_TOKEN}` },
});
```

The recording is created.

## The "Stream pricing" pattern

For pricing:
- **Storage:** Per minute stored
- **Delivery:** Per minute delivered
- **Encoding:** Included

The pricing is per minute.

## The "Stream limits" pattern

For limits:
- **Max upload:** 30 GB per file
- **Concurrent encodes:** 120 per account
- **Storage:** Per subscription
- **Frame rate:** Up to 70 FPS

The limits are checked.

## The "recommended upload" pattern

For upload best practices:
- **MP4:** Container
- **AAC:** Audio
- **H.264:** Video
- **30-60 FPS:** Standard
- **Closed GOP:** Required for live
- **Stereo:** Audio channels
- **moov atom at front:** Fast start

The upload is optimized.

## The "Stream + R2" pattern

For R2 + Stream:
- **R2:** Custom files
- **Stream:** Video delivery

The right tool per use case.

## The "Stream anti-pattern" anti-patterns

### 1. Self-hosted transcoding
- **Issue:** Heavy CPU
- **Fix:** Stream

### 2. No adaptive bitrate
- **Issue:** Slow on mobile
- **Fix:** Stream

### 3. No portrait
- **Issue:** Vertical video is small
- **Fix:** Stream (native)

### 4. No CSP
- **Issue:** Blocked
- **Fix:** Add Stream to CSP

### 5. No thumbnail
- **Issue:** Empty UI
- **Fix:** Generate thumbnail

## Verification
- **Test:** Upload works
- **Test:** Encoding completes
- **Test:** Playback works
- **Test:** Adaptive bitrate works
- **Live:** Usage monitored
- **Audit:** Quarterly review

## Gotchas
- **The "self-hosted transcoding" anti-pattern.** Use
  Stream.
- **The "no adaptive bitrate" anti-pattern.** Stream
  does it.
- **The "no CSP" anti-pattern.** Add Stream to CSP.

## Related
- `cloudflare/realtime-sfu-best-practices.md`
- `cloudflare/r2-best-practices.md`
- `feature-cookbook-file-upload.md`
- CF Stream: https://developers.cloudflare.com/stream/
- Stream Live: https://developers.cloudflare.com/stream/stream-live/
