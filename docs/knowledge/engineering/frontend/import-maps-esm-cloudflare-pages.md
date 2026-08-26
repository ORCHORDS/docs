# Import Maps and Native ESM on Cloudflare Pages

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A project wants to load ES modules natively in the browser without a bundler step, or needs to remap bare specifiers (`import { h } from "preact"`) to a CDN URL in production while a local import map points to `node_modules`. Cloudflare Pages can serve the import map via a Worker or static `_headers`, enabling a no-bundle workflow.

## Context

Import maps are now baseline-available across all evergreen browsers (Chrome 89+, Firefox 108+, Safari 16.4+). They let you define a JSON mapping from bare specifiers to URLs, keeping source code free of full CDN paths. Cloudflare Pages static hosting serves the JSON file; an optional Pages Function can inject a nonce-hashed map into SSR responses for stricter CSP. This pattern pairs well with islands architecture, where each island is a self-contained ES module loaded on demand.

## Authoring the Import Map

```json
// public/importmap.json
{
  "imports": {
    "preact": "https://esm.sh/preact@10.22.0",
    "preact/": "https://esm.sh/preact@10.22.0/",
    "preact/hooks": "https://esm.sh/preact@10.22.0/hooks",
    "@/": "/src/"
  },
  "scopes": {
    "/src/islands/": {
      "htm/preact": "https://esm.sh/htm@3.1.1/preact"
    }
  }
}
```

Inline it in HTML during the build step or inject it via a Worker for dynamic nonce-based CSP.

## Injecting the Map at the Edge

```typescript
// functions/_middleware.ts
const IMPORT_MAP_URL = "/importmap.json";

export const onRequest: PagesFunction<Env> = async (context) => {
  const response = await context.next();
  const contentType = response.headers.get("content-type") ?? "";

  if (!contentType.includes("text/html")) return response;

  // Fetch the map from the same origin (cached at edge after first load)
  const mapRes = await fetch(
    new URL(IMPORT_MAP_URL, context.request.url).toString(),
    { cf: { cacheEverything: true, cacheTtl: 86400 } }
  );
  const map = await mapRes.text();

  return new HTMLRewriter()
    .on("head", {
      element(el) {
        el.prepend(
          `<script type="importmap">${map}</script>`,
          { html: true }
        );
      },
    })
    .transform(response);
};
```

## Type-Safe Env Binding

```typescript
// types/env.d.ts
export interface Env {
  ASSETS: Fetcher;          // Pages static assets binding
  IMPORT_MAP_KV: KVNamespace; // optional: store map in KV for instant updates
}

declare module "@cloudflare/workers-types" {
  interface CfProperties {
    cacheEverything?: boolean;
    cacheTtl?: number;
  }
}
```

```typescript
// functions/_middleware.ts — KV-backed map for zero-deploy updates
export const onRequest: PagesFunction<Env> = async (context) => {
  const response = await context.next();
  if (!response.headers.get("content-type")?.includes("text/html")) {
    return response;
  }

  const map =
    (await context.env.IMPORT_MAP_KV.get("current")) ??
    (await fetch(new URL("/importmap.json", context.request.url)).then((r) =>
      r.text()
    ));

  return new HTMLRewriter()
    .on("head", {
      element: (el) =>
        el.prepend(`<script type="importmap">${map}</script>`, {
          html: true,
        }),
    })
    .transform(response);
};
```

## Island Entry Points with Bare Specifiers

```tsx
// src/islands/counter.tsx — runs in the browser, no bundler
import { useState } from "preact/hooks";

interface CounterProps {
  initial?: number;
}

export function Counter({ initial = 0 }: CounterProps) {
  const [count, setCount] = useState(initial);
  return (
    <div class="counter">
      <button onClick={() => setCount((n) => n - 1)}>−</button>
      <output>{count}</output>
      <button onClick={() => setCount((n) => n + 1)}>+</button>
    </div>
  );
}
```

```html
<!-- public/index.html — importmap already injected by Worker -->
<script type="module">
  import { render } from "preact";
  import { Counter } from "@/islands/counter.tsx";

  const el = document.getElementById("counter-root");
  if (el) render(<Counter initial={0} />, el);
</script>
```

Note: TSX in the browser requires a transform step or a `<script type="module"  transform>` shim from esm.sh.

## Build-Time Integrity Hashing

For production, add `integrity` attributes to the map entries using SRI hashes.

```typescript
// scripts/hash-import-map.ts
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

async function addIntegrity(mapPath: string): Promise<void> {
  const map = JSON.parse(readFileSync(mapPath, "utf8")) as {
    imports: Record<string, string>;
  };

  const resolved: Record<string, string> = {};
  for (const [specifier, url] of Object.entries(map.imports)) {
    const res = await fetch(url);
    const buf = await res.arrayBuffer();
    const hash = createHash("sha384").update(Buffer.from(buf)).digest("base64");
    resolved[specifier] = url;
    console.log(`${specifier}: sha384-${hash}`);
  }

  writeFileSync(
    mapPath.replace(".json", ".sri.json"),
    JSON.stringify({ imports: resolved, integrity: {} }, null, 2)
  );
}

addIntegrity("public/importmap.json");
```

## Anti-patterns

- Using an import map in production without a fallback — older Safari and all IE users silently break
- Pointing import map specifiers at unversioned CDN URLs — cache busting becomes impossible
- Mixing bundled and unbundled specifiers in the same app without scoping — creates duplicate module instances
- Putting the `<script type="importmap">` tag after any `<script type="module">` — browsers reject maps declared after module scripts

## Gotchas

- Import maps are processed before any module fetches begin; injecting them after DOMContentLoaded via JS has no effect
- `HTMLRewriter` operates on a streaming byte sequence; large import maps (>64 KB) can stall the transform pipeline
- `esm.sh` URLs include peer dependencies implicitly; pin both the package and its peers to avoid version drift
- When injecting via `_middleware.ts`, ensure the import map JSON does not contain `</script>` sequences that break the inline tag

## Verification

1. Open DevTools → Application → Module Map — all bare specifiers should resolve to the expected CDN URLs.
2. Run `npx es-module-shims audit --url https://<project>.pages.dev/` to check browser compatibility.
3. In Playwright: `await page.evaluate(() => document.querySelectorAll('script[type="importmap"]').length)` should return 1.

## Related

- [code-splitting-dynamic-import.md](code-splitting-dynamic-import.md)
- [tree-shaking-patterns.md](tree-shaking-patterns.md)
- [web-components-cloudflare-workers-html-rewriter.md](web-components-cloudflare-workers-html-rewriter.md)
- [vite-config-patterns.md](vite-config-patterns.md)

## Sources

- https://developer.mozilla.org/en-US/docs/Web/HTML/Element/script/type/importmap
- https://wicg.github.io/import-maps/
- https://esm.sh
- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
