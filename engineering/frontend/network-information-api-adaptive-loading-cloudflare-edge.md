# Network Information API — Adaptive Loading at Cloudflare Edge

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project serves anonymous users globally including mobile users on 2G/3G connections. Heavy
assets — avatar images, video previews, WebSocket connections — degrade their experience.
You want to serve a lighter bundle or skip expensive fetches when the user is on a slow
connection, without a server round-trip to detect it.

## Context

The Network Information API (`navigator.connection`) exposes `effectiveType` (4g/3g/2g/slow-2g),
`downlink` (Mbps), `rtt` (ms), and `saveData` (Data Saver flag). Combined with the
`Client Hints` header `ECT` (Effective Connection Type) that Cloudflare can forward, you
can make adaptive decisions both in the browser and at the edge without extra latency.

Browser support: Chrome/Edge/Android WebView. Firefox and Safari do not implement it; always
provide a sensible default for unsupported browsers.

## Browser-Side: Reading Network Conditions

```typescript
// src/lib/network.ts
export type ConnectionQuality = "fast" | "medium" | "slow" | "unknown";

export function getConnectionQuality(): ConnectionQuality {
  const conn = (navigator as Navigator & {
    connection?: {
      effectiveType: string;
      downlink: number;
      rtt: number;
      saveData: boolean;
    };
  }).connection;

  if (!conn) return "unknown";
  if (conn.saveData) return "slow";
  switch (conn.effectiveType) {
    case "4g": return conn.downlink >= 5 ? "fast" : "medium";
    case "3g": return "medium";
    case "2g":
    case "slow-2g": return "slow";
    default: return "unknown";
  }
}

export function onConnectionChange(cb: (quality: ConnectionQuality) => void): () => void {
  const conn = (navigator as any).connection;
  if (!conn) return () => {};
  const handler = () => cb(getConnectionQuality());
  conn.addEventListener("change", handler);
  return () => conn.removeEventListener("change", handler);
}
```

## React Hook: Adaptive Asset Loading

```typescript
// src/hooks/useAdaptiveLoading.ts
import { useState, useEffect } from "react";
import { getConnectionQuality, onConnectionChange, ConnectionQuality } from "../lib/network";

export function useAdaptiveLoading() {
  const [quality, setQuality] = useState<ConnectionQuality>(() => {
    if (typeof navigator === "undefined") return "unknown";
    return getConnectionQuality();
  });

  useEffect(() => {
    setQuality(getConnectionQuality());
    return onConnectionChange(setQuality);
  }, []);

  return {
    quality,
    shouldLoadVideo: quality === "fast",
    shouldPreloadImages: quality !== "slow",
    imageFormat: quality === "slow" ? "webp" : "avif",
    prefetchEnabled: quality === "fast" || quality === "unknown",
  };
}
```

## Adaptive Image Component

```tsx
// src/components/AdaptiveImage.tsx
import { useAdaptiveLoading } from "../hooks/useAdaptiveLoading";

interface Props {
  src: string;        // R2 object key, e.g. "avatars/abc123"
  alt: string;
  width: number;
  height: number;
}

const WORKER_URL = "https://img.example.com";

export function AdaptiveImage({ src, alt, width, height }: Props) {
  const { imageFormat, quality, shouldPreloadImages } = useAdaptiveLoading();

  // Downscale resolution on slow connections
  const scale = quality === "slow" ? 0.5 : quality === "medium" ? 0.75 : 1;
  const w = Math.round(width * scale);
  const h = Math.round(height * scale);

  const url = `${WORKER_URL}/${src}?w=${w}&h=${h}&fmt=${imageFormat}`;

  return (
    <img
      src={url}
      alt={alt}
      width={width}
      height={height}
      loading={shouldPreloadImages ? "eager" : "lazy"}
      decoding="async"
      style={{ aspectRatio: `${width}/${height}` }}
    />
  );
}
```

## Edge: Client Hints in Cloudflare Workers

```typescript
// functions/api/feed.ts  (Cloudflare Pages Function)
export const onRequestGet: PagesFunction = async ({ request }) => {
  // Cloudflare propagates the ECT client hint when the browser sends it
  // Requires: <meta http-equiv="Accept-CH" content="ECT,Downlink,RTT,Save-Data">
  const ect = request.headers.get("ECT") ?? "4g";
  const saveData = request.headers.get("Save-Data") === "on";

  const isSlowConnection = saveData || ect === "2g" || ect === "slow-2g";

  // Return a stripped-down feed for slow connections
  const feedUrl = isSlowConnection
    ? "https://api.example.com/feed?lite=1"
    : "https://api.example.com/feed";

  const upstream = await fetch(feedUrl, {
    headers: { "X-ECT": ect },
  });

  const response = new Response(upstream.body, upstream);
  response.headers.set("Vary", "ECT, Save-Data");
  return response;
};
```

## Enabling Client Hints (HTML / Next.js)

```html
<!-- public/index.html or _document.tsx -->
<!-- Opt in to receiving network client hints on future requests -->
<meta http-equiv="Accept-CH" content="ECT, Downlink, RTT, Save-Data" />
<meta http-equiv="Permissions-Policy" content="ch-ect=*, ch-downlink=*, ch-save-data=*" />
```

```typescript
// next.config.ts — propagate Accept-CH via response headers
export default {
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Accept-CH", value: "ECT, Downlink, RTT, Save-Data" },
          { key: "Critical-CH", value: "ECT" },
        ],
      },
    ];
  },
};
```

## Preventing Layout Shift on Quality Change

```typescript
// src/hooks/useStableAdaptiveLoading.ts
import { useRef } from "react";
import { useAdaptiveLoading } from "./useAdaptiveLoading";
import { ConnectionQuality } from "../lib/network";

// Only ever downgrade; never re-fetch a higher-quality asset mid-session
export function useStableAdaptiveLoading() {
  const { quality, ...rest } = useAdaptiveLoading();
  const stableRef = useRef<ConnectionQuality>(quality);

  // Once we've detected "fast", stay fast for the session lifetime
  if (
    (stableRef.current === "slow" && quality !== "slow") ||
    stableRef.current === "unknown"
  ) {
    stableRef.current = quality;
  }

  return { quality: stableRef.current, ...rest };
}
```

## Anti-patterns

- **Blocking render on connection detection** — The API is synchronous but unreliable on
  first read; use a default and update reactively.
- **Sending ECT in custom headers without `Vary`** — Cloudflare will cache the wrong variant;
  always add `Vary: ECT, Save-Data`.
- **Trusting `effectiveType` as ground truth** — It is an estimate derived from recent RTT
  samples; treat it as a hint, not a guarantee.
- **Shipping two separate JS bundles** — Conditional data fetching is enough; don't duplicate
  the entire chunk graph for connection quality.

## Gotchas

- `navigator.connection` is `undefined` in Firefox, Safari, and SSR contexts; guard every
  access.
- Client Hints are only sent after the first response sets `Accept-CH`; the very first page
  load never carries ECT. Use `Critical-CH` to retry immediately.
- Cloudflare Workers only receive Client Hints if the browser and CF plan support it (Business
  or Enterprise for request header forwarding; available on all plans via `CF-Device-Type`).
- `saveData: true` overrides `effectiveType`; check it first.

## Verification

```bash
# Simulate slow-2g in Chrome DevTools → Network tab → throttle preset
# Then check: navigator.connection.effectiveType === "slow-2g"

# Check edge receives ECT header
curl -H "ECT: slow-2g" https://example.com/api/feed -v 2>&1 | grep -i ect
```

## Related

- `compute-pressure-api-cloudflare-pages-adaptive-ui.md`
- `nextjs-image-optimization-cloudflare-pages.md`
- `image-format-selection-webp-avif.md`
- `cloudflare-workers-ai-edge-inference-ui.md`
- `html-lazy-loading-images.md`

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/NetworkInformation
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/ECT
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://web.dev/articles/adaptive-serving-based-on-network-quality
