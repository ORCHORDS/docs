# HTTP 103 Early Hints on Cloudflare Pages

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

LCP scores are hurt by the browser waiting for the full HTML response before it can discover and fetch critical CSS, fonts, and hero images. HTTP 103 Early Hints lets the server stream preload headers before the final 200 response is ready.

## Context

Cloudflare Workers can emit a `103 Early Hints` informational response before the actual body response. The browser receives the preload hints immediately, starts fetching assets in parallel, and the final 200 response arrives with the completed HTML. This is most impactful on origin-rendered pages where Workers SSR takes 50–150 ms. Cloudflare's edge has native support for forwarding 103 responses since 2022; Pages Functions inherit this support.

## Emitting 103 from a Pages Function

Place a `functions/_middleware.ts` file. For route-specific hints, co-locate in `functions/[route].ts`.

```typescript
// functions/_middleware.ts
import type { EventContext } from "@cloudflare/workers-types";

const CRITICAL_ASSETS: string[] = [
  "</fonts/inter-var.woff2>; rel=preload; as=font; crossorigin",
  "</styles/main.css>; rel=preload; as=style",
  "</images/hero.avif>; rel=preload; as=image; fetchpriority=high",
];

export const onRequest: PagesFunction = async (context) => {
  // Emit 103 before awaiting the downstream handler
  const earlyHints = new Response(null, {
    status: 103,
    headers: {
      Link: CRITICAL_ASSETS.join(", "),
    },
  });

  // Workers runtime surfaces 103 to the edge; the client receives it
  // before the handler resolves. We must still return the real response.
  context.waitUntil(Promise.resolve(earlyHints));

  const response = await context.next();
  // Repeat the Link header on the 200 so HTTP/1.1 clients benefit too
  const headers = new Headers(response.headers);
  headers.set("Link", CRITICAL_ASSETS.join(", "));
  return new Response(response.body, { ...response, headers });
};
```

## Configuring Per-Route Hints

Different routes have different critical paths. Use a lookup table keyed on pathname prefix.

```typescript
// functions/_middleware.ts
type HintMap = Record<string, string[]>;

const ROUTE_HINTS: HintMap = {
  "/": [
    "</fonts/inter-var.woff2>; rel=preload; as=font; crossorigin",
    "</images/hero.avif>; rel=preload; as=image",
  ],
  "/blog/": [
    "</fonts/inter-var.woff2>; rel=preload; as=font; crossorigin",
    "</styles/prism.css>; rel=preload; as=style",
  ],
};

function hintsForPath(pathname: string): string[] {
  for (const [prefix, hints] of Object.entries(ROUTE_HINTS)) {
    if (pathname.startsWith(prefix)) return hints;
  }
  return [];
}

export const onRequest: PagesFunction = async (context) => {
  const { pathname } = new URL(context.request.url);
  const hints = hintsForPath(pathname);

  if (hints.length > 0) {
    // The Workers runtime delivers this 103 to the CDN edge
    context.waitUntil(
      Promise.resolve(
        new Response(null, {
          status: 103,
          headers: { Link: hints.join(", ") },
        })
      )
    );
  }

  return context.next();
};
```

## Combining with `<link rel="preload">` in HTML

Early Hints and in-HTML preloads are complementary: 103 fires before HTML is parsed, the in-HTML tag fires during parse. Keep them in sync with a shared manifest.

```typescript
// lib/asset-manifest.ts
export interface AssetManifest {
  fonts: string[];
  styles: string[];
  images: string[];
}

export const MANIFEST: AssetManifest = {
  fonts: ["/fonts/inter-var.woff2"],
  styles: ["/styles/main.css"],
  images: [],          // filled dynamically per-route
};

export function toLinkHeaders(manifest: AssetManifest): string[] {
  return [
    ...manifest.fonts.map(
      (f) => `<${f}>; rel=preload; as=font; crossorigin`
    ),
    ...manifest.styles.map((s) => `<${s}>; rel=preload; as=style`),
    ...manifest.images.map(
      (i) => `<${i}>; rel=preload; as=image; fetchpriority=high`
    ),
  ];
}
```

```tsx
// app/layout.tsx (React / Next.js on Pages)
import { MANIFEST } from "@/lib/asset-manifest";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {MANIFEST.fonts.map((href) => (
          <link key={href} rel="preload" href={href} as="font" crossOrigin="anonymous" />
        ))}
        {MANIFEST.styles.map((href) => (
          <link key={href} rel="preload" href={href} as="style" />
        ))}
      </head>
      <body>{children}</body>
    </html>
  );
}
```

## Verifying with Chrome DevTools

```typescript
// scripts/check-early-hints.ts — run with `npx tsx`
async function checkEarlyHints(url: string): Promise<void> {
  // Node 18+ fetch does not surface 103; use curl in CI
  const { execSync } = await import("node:child_process");
  const output = execSync(
    `curl -sI --http2 -w "\\n%{response_code}" "${url}"`,
    { encoding: "utf8" }
  );
  const has103 = output.includes("HTTP/2 103");
  console.log(has103 ? "103 Early Hints present" : "No 103 detected");
  console.log(output);
}

checkEarlyHints("https://example.pages.dev/");
```

## Anti-patterns

- Preloading assets that are not used on the page — wastes bandwidth and competes with real critical resources
- Emitting 103 hints for third-party origins without `crossorigin` where required (fonts, CORS assets)
- Using 103 for non-critical below-the-fold images — increases contention on the HTTP/2 multiplexed connection
- Sending duplicate `Link` headers in both 103 and 200 with conflicting `rel` values

## Gotchas

- Workers `waitUntil` does not guarantee the 103 is delivered before the body; Cloudflare's runtime handles timing internally. Do not rely on ordering in tests.
- HTTP/1.1 clients ignore 103; always repeat critical `Link` headers on the 200 response.
- Safari support for 103 arrived in 2024 — verify with Can I Use before removing in-HTML fallback preloads.
- Large `Link` header values (>8 KB) can be rejected by some proxies sitting between Cloudflare and the client.

## Verification

1. Deploy to Cloudflare Pages and run `curl -sI --http2 https://<project>.pages.dev/` — look for `HTTP/2 103` before `HTTP/2 200`.
2. In Chrome DevTools → Network tab, filter by the font/image URL and check the "Initiator" column for "Push / Early Hints".
3. Run a WebPageTest trace with "Capture Lighthouse" enabled — LCP timing should decrease compared to a baseline without hints.

## Related

- [html-performance-resource-hints.md](html-performance-resource-hints.md)
- [html-web-vitals-lcp.md](html-web-vitals-lcp.md)
- [priority-hints-fetchpriority-lcp.md](priority-hints-fetchpriority-lcp.md)
- [nextjs-partial-prerendering-cloudflare.md](nextjs-partial-prerendering-cloudflare.md)

## Sources

- https://developer.chrome.com/blog/early-hints/
- https://developers.cloudflare.com/cache/advanced-configuration/early-hints/
- https://www.rfc-editor.org/rfc/rfc8297 (HTTP 103 Informational Responses)
- https://web.dev/articles/fetch-priority
