# Media Session API — OS-Level Playback Controls on Cloudflare Pages

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A streaming audio or video player hosted on Cloudflare Pages shows no artwork or
track title in the macOS Control Center, iOS lock screen, or Android notification
shade. Hardware media keys (play/pause, skip, scrub) do nothing. Seek bars in the
OS widget show 0:00 permanently even while content plays. The browser's PiP
thumbnail shows a blank frame because no metadata was ever registered.

## Context

`navigator.mediaSession` bridges your in-page media state to the operating system's
media hub. When populated, the OS widget, lock-screen controls, and Bluetooth device
buttons all delegate to your page's callbacks. The API is entirely client-side;
Cloudflare Pages is purely a static-asset host here. Workers are useful only for
serving signed source URLs or generating JSON track manifests — the session metadata
work lives in the browser exclusively.

Browser support: Chrome 73+, Firefox 82+, Safari 15+, Edge 79+. The API is not
available inside iframes unless the `allow="media"` attribute is present. Always
feature-detect before use.

---

## 1. Setting Metadata

```typescript
interface TrackMetadata {
  title: string;
  artist: string;
  album: string;
  artwork: Array<{ src: string; sizes: string; type: string }>;
}

function setMediaMetadata(track: TrackMetadata): void {
  if (!('mediaSession' in navigator)) return;

  navigator.mediaSession.metadata = new MediaMetadata({
    title: track.title,
    artist: track.artist,
    album: track.album,
    artwork: track.artwork,
  });
}

setMediaMetadata({
  title: 'Evening Session',
  artist: 'Claude Debussy',
  album: 'Préludes, Book I',
  artwork: [
    { src: '/artwork/96.jpg',   sizes: '96x96',     type: 'image/jpeg' },
    { src: '/artwork/512.jpg',  sizes: '512x512',   type: 'image/jpeg' },
    { src: '/artwork/1024.jpg', sizes: '1024x1024', type: 'image/jpeg' },
  ],
});
```

The OS fetches artwork directly from the `src` URLs. Host images on Cloudflare Pages
or an R2 public bucket. CORS headers are not required here because the OS agent
makes the request outside the page's origin context.

---

## 2. Registering Action Handlers

```typescript
type SeekCallback = (details: MediaSessionActionDetails) => void;

function registerPlayerActions(audio: HTMLAudioElement): void {
  if (!('mediaSession' in navigator)) return;

  const seek: SeekCallback = ({ seekTime, seekOffset }) => {
    if (seekTime != null) {
      audio.currentTime = seekTime;
    } else if (seekOffset != null) {
      audio.currentTime = Math.max(0, audio.currentTime + seekOffset);
    }
  };

  navigator.mediaSession.setActionHandler('play',          () => audio.play());
  navigator.mediaSession.setActionHandler('pause',         () => audio.pause());
  navigator.mediaSession.setActionHandler('stop',          () => { audio.pause(); audio.currentTime = 0; });
  navigator.mediaSession.setActionHandler('seekbackward',  seek);
  navigator.mediaSession.setActionHandler('seekforward',   seek);
  navigator.mediaSession.setActionHandler('seekto',        seek);
  navigator.mediaSession.setActionHandler('previoustrack', () => loadTrack('prev'));
  navigator.mediaSession.setActionHandler('nexttrack',     () => loadTrack('next'));
}
```

Handlers that throw do not propagate to the OS; wrap risky code in try/catch. If
`previoustrack` is not registered, some platforms hide that button entirely.

---

## 3. Keeping Playback Position in Sync

Without `setPositionState`, the OS seek bar never moves and shows 0:00 permanently.

```typescript
function updatePositionState(audio: HTMLAudioElement): void {
  if (!('mediaSession' in navigator)) return;
  if (!audio.duration || !isFinite(audio.duration)) return;

  try {
    navigator.mediaSession.setPositionState({
      duration:     audio.duration,
      playbackRate: audio.playbackRate,
      position:     audio.currentTime,
    });
  } catch {
    // duration may not be available mid-stream on some codecs
  }
}

function attachPositionSync(audio: HTMLAudioElement): () => void {
  const sync = () => updatePositionState(audio);
  audio.addEventListener('timeupdate',    sync);
  audio.addEventListener('durationchange', sync);
  audio.addEventListener('ratechange',    sync);
  return () => {
    audio.removeEventListener('timeupdate',    sync);
    audio.removeEventListener('durationchange', sync);
    audio.removeEventListener('ratechange',    sync);
  };
}
```

---

## 4. Mirroring Playback State

```typescript
type PlaybackState = 'none' | 'paused' | 'playing';

function mirrorPlaybackState(audio: HTMLAudioElement): () => void {
  const sync = () => {
    if (!('mediaSession' in navigator)) return;
    navigator.mediaSession.playbackState = audio.paused ? 'paused' : 'playing';
  };

  const onEnded = () => {
    if ('mediaSession' in navigator) navigator.mediaSession.playbackState = 'none';
  };

  audio.addEventListener('play',  sync);
  audio.addEventListener('pause', sync);
  audio.addEventListener('ended', onEnded);

  return () => {
    audio.removeEventListener('play',  sync);
    audio.removeEventListener('pause', sync);
    audio.removeEventListener('ended', onEnded);
  };
}
```

The OS control widget reads `playbackState` to decide whether to render a play or
pause icon. Without this it may desync from the actual audio element state after
brief network stalls.

---

## 5. Workers: Serving Signed Track Manifests

A Cloudflare Worker can assemble a JSON manifest including a time-limited R2
artwork URL so secret signing keys never reach the client bundle.

```typescript
// workers/track-manifest.ts
interface TrackRecord {
  title: string;
  artist: string;
  album: string;
  artwork_path: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const trackId = new URL(request.url).searchParams.get('id');
    if (!trackId) return new Response('Missing id', { status: 400 });

    const record = await env.DB
      .prepare('SELECT title, artist, album, artwork_path FROM tracks WHERE id = ?')
      .bind(trackId)
      .first<TrackRecord>();

    if (!record) return new Response('Not found', { status: 404 });

    const signedArtwork = await signR2Url(env, record.artwork_path, 3600);

    return Response.json(
      {
        title:   record.title,
        artist:  record.artist,
        album:   record.album,
        artwork: [{ src: signedArtwork, sizes: '512x512', type: 'image/jpeg' }],
      },
      { headers: { 'Cache-Control': 'private, max-age=3600' } }
    );
  },
} satisfies ExportedHandler<Env>;
```

---

## Anti-patterns

- Setting metadata before the user gesture that starts playback. Some browsers
  discard metadata set before the first `play()` call resolves.
- Omitting `setPositionState`: the OS seek bar never moves regardless of
  `timeupdate` events.
- Syncing only on `timeupdate` and ignoring `durationchange`. Live streams announce
  their duration late; without `durationchange` the position state is always stale.
- Providing artwork at only one resolution. The OS selects the most appropriate
  size; always supply at minimum 96×96 and 512×512 variants.
- Removing action handlers when the track ends but leaving stale metadata. Always
  set `playbackState = 'none'` and clear the metadata on playlist exhaustion.

## Gotchas

- `seekto` required the `fastSeek` feature flag in Firefox 82–87; test explicitly
  on that range.
- On iOS, the lock-screen widget appears only after a user-gesture-initiated
  `play()` call. Autoplay via the `autoplay` attribute does not trigger it.
- `MediaMetadata` is not a plain object; `JSON.stringify(navigator.mediaSession.metadata)`
  returns `"{}"`. Read fields individually.
- Cloudflare's default `Cache-Control` on R2 public buckets may serve stale artwork
  if a track is updated without changing the URL. Use cache-busting query params or
  versioned paths.
- The API is blocked in iframes without an explicit `allow="mediasession"` permission
  policy — this differs from the `allow="media"` attribute that unblocks playback.

## Verification

```typescript
// Confirm metadata round-trip
navigator.mediaSession.metadata = new MediaMetadata({ title: 'Smoke test' });
console.assert(navigator.mediaSession.metadata?.title === 'Smoke test');

// Confirm action handlers fire
navigator.mediaSession.setActionHandler('play', () => console.log('play fired'));
// Trigger via hardware key or OS widget, observe console
```

Open Chrome DevTools → Application → Media to inspect the active `MediaSession`,
its metadata, and active action handlers in real time.

## Related

- `screen-wake-lock-visibility-lifecycle.md`
- `video-autoplay-mobile-restrictions-hls.md`
- `pwa-service-worker-cloudflare-pages.md`
- `cloudflare-r2-presigned-upload-frontend.md`

## Sources

- WHATWG Media Session Standard — https://w3c.github.io/mediasession/
- MDN MediaSession — https://developer.mozilla.org/en-US/docs/Web/API/MediaSession
- Chrome Developers: Media Session API — https://developer.chrome.com/docs/capabilities/web-apis/media-session
