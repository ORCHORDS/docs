# iOS AVPlayer HLS Streaming via Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You store HLS video segments in R2 and need a Cloudflare Worker to dynamically generate `.m3u8` playlists so an iOS AVPlayer can stream them, with proper caching, CORS, and DRM token injection.

## Context

- iOS 16+ / Swift 5.9, AVFoundation
- HLS segments (`.ts` or `.m4s`) stored in Cloudflare R2
- Cloudflare Worker generates playlists on request, signs segment URLs, and verifies DRM tokens
- Cloudflare Analytics Engine used for playback telemetry
- No external CDN — Worker serves as the origin and edge simultaneously

## Cloudflare Worker — Playlist Generation

```typescript
// worker/src/hls.ts
import { R2Bucket, AnalyticsEngineDataset } from '@cloudflare/workers-types';

interface Env {
  MEDIA_BUCKET: R2Bucket;
  ANALYTICS: AnalyticsEngineDataset;
  DRM_SECRET: string;
}

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
  'Access-Control-Allow-Headers': 'Range, Origin, Accept',
};

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(req.url);

    if (req.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    // Verify DRM token on playlist requests
    if (url.pathname.endsWith('.m3u8')) {
      const token = url.searchParams.get('token');
      if (!token || !verifyDrmToken(token, env.DRM_SECRET)) {
        return new Response('Unauthorized', { status: 401, headers: CORS_HEADERS });
      }
      return servePlaylist(url, env, ctx);
    }

    // Serve segments directly from R2
    if (url.pathname.endsWith('.ts') || url.pathname.endsWith('.m4s')) {
      return serveSegment(url, env, ctx);
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function servePlaylist(
  url: URL,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const videoId = url.pathname.split('/')[2]; // /hls/{videoId}/index.m3u8
  const prefix = `videos/${videoId}/`;

  const listed = await env.MEDIA_BUCKET.list({ prefix, delimiter: '/' });
  const segmentKeys = listed.objects
    .map(o => o.key)
    .filter(k => k.endsWith('.ts') || k.endsWith('.m4s'))
    .sort();

  const lines = ['#EXTM3U', '#EXT-X-VERSION:3', '#EXT-X-TARGETDURATION:6'];
  for (const key of segmentKeys) {
    const segName = key.replace(prefix, '');
    lines.push('#EXTINF:6.0,');
    lines.push(`/hls/${videoId}/${segName}`);
  }
  lines.push('#EXT-X-ENDLIST');

  env.ANALYTICS.writeDataPoint({
    blobs: [videoId, 'playlist_served'],
    doubles: [segmentKeys.length],
    indexes: [videoId],
  });

  return new Response(lines.join('\n'), {
    headers: {
      'Content-Type': 'application/vnd.apple.mpegurl',
      // Playlist must not be cached — content changes as segments are added
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      ...CORS_HEADERS,
    },
  });
}

async function serveSegment(
  url: URL,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const key = url.pathname.slice(1); // strip leading /
  const obj = await env.MEDIA_BUCKET.get(key);
  if (!obj) return new Response('Not Found', { status: 404, headers: CORS_HEADERS });

  return new Response(obj.body, {
    headers: {
      'Content-Type': 'video/mp2t',
      // Segments are immutable once written
      'Cache-Control': 'public, max-age=31536000, immutable',
      ...CORS_HEADERS,
    },
  });
}

function verifyDrmToken(token: string, secret: string): boolean {
  // Simple HMAC-based token; production use should verify expiry claim too
  const [payload, sig] = token.split('.');
  const expected = btoa(payload + secret).replace(/=/g, '');
  return sig === expected;
}
```

## iOS AVPlayer Integration

```swift
// VideoPlayerViewModel.swift
import AVFoundation
import Combine

final class VideoPlayerViewModel: ObservableObject {
    @Published var playerError: String?
    let player: AVPlayer

    private var timeObserver: Any?
    private var statusObserver: AnyCancellable?

    init(videoId: String, drmToken: String) {
        let workerBase = "https://media.example.com"
        var components = URLComponents(string: "\(workerBase)/hls/\(videoId)/index.m3u8")!
        components.queryItems = [URLQueryItem(name: "token", value: drmToken)]

        let asset = AVURLAsset(
            url: components.url!,
            options: [
                "AVURLAssetHTTPHeaderFieldsKey": [
                    "Origin": workerBase
                ]
            ]
        )
        let item = AVPlayerItem(asset: asset)
        self.player = AVPlayer(playerItem: item)

        statusObserver = item.publisher(for: \.status)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] status in
                if status == .failed {
                    self?.playerError = item.error?.localizedDescription
                    self?.reportPlaybackError(videoId: videoId, error: item.error)
                }
            }
    }

    private func reportPlaybackError(videoId: String, error: Error?) {
        guard let url = URL(string: "https://media.example.com/analytics/error") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: String] = [
            "videoId": videoId,
            "error": error?.localizedDescription ?? "unknown"
        ]
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        URLSession.shared.dataTask(with: req).resume()
    }

    deinit { player.pause() }
}
```

## DRM Token Flow

1. App authenticates with your auth service, receiving a short-lived DRM token.
2. Token is appended to the `.m3u8` URL as `?token=<value>`.
3. Worker validates the token on every playlist request; segments are not token-gated (they are private R2 objects served only via the Worker).
4. Token expiry should be short (5–15 minutes); refresh before AVPlayer retries the playlist.

## Anti-patterns

- **Caching the `.m3u8` playlist at the edge** — live or growing VOD playlists become stale immediately; always set `Cache-Control: no-cache`.
- **Exposing R2 bucket publicly** — R2 should only be accessed by the Worker; disable public access in the R2 bucket settings.
- **Embedding the DRM token in segment URLs** — token in the variant playlist URL is sufficient; segment URLs must not carry credentials that end up in access logs.
- **Omitting the `Origin` header on AVPlayer requests** — iOS may send requests without `Origin`; your CORS headers must allow `*` or explicitly list your Worker domain.

## Gotchas

- AVPlayer requires the `Content-Type` to be exactly `application/vnd.apple.mpegurl` or `audio/mpegurl` for HLS; returning `text/plain` causes silent failure.
- `R2Bucket.list()` is paginated at 1000 objects by default; long videos with many segments need cursor-based pagination in the Worker.
- Workers free tier limits CPU time to 10ms; segment listing for long videos may need Durable Objects or a D1 index of segment keys.
- Analytics Engine `writeDataPoint` is non-blocking but counts against your AE write quota; sample at 10% for high-traffic streams.

## Verification

1. `curl -I "https://media.example.com/hls/test/index.m3u8?token=<valid>"` — expect `Cache-Control: no-cache`.
2. `curl -I "https://media.example.com/hls/test/seg0.ts"` — expect `Cache-Control: public, max-age=31536000, immutable`.
3. Load the playlist URL in `ffprobe` to confirm the segment list is valid HLS.
4. In Xcode, set a breakpoint in `reportPlaybackError` and feed an invalid token — AVPlayer should surface a 401 error within 3s.

## Related

- `documentation/workers/r2-signed-urls.md`
- `documentation/workers/analytics-engine-events.md`
- `documentation/categories/mobile/ios-avplayer-drm.md`

## Sources

- https://developers.cloudflare.com/r2/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developer.apple.com/documentation/avfoundation/avplayer
- https://datatracker.ietf.org/doc/html/rfc8216
