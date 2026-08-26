# Alpine.js on Cloudflare Pages with a Strict CSP

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Alpine.js evaluates `x-data` and `x-on` directives with `Function()` (effectively `eval`) at runtime, which is blocked by a `Content-Security-Policy: script-src 'self'` header without `'unsafe-eval'`. Cloudflare Pages supports custom response headers via `_headers` files, so teams adopting a strict CSP to satisfy PCI-DSS or SOC 2 requirements must either switch to Alpine's CSP-compatible build or restructure their directives to avoid inline evaluation. This article covers both the CSP-safe Alpine build path and the Cloudflare Pages `_headers` configuration.

## Context

Alpine.js v3 ships two builds: the standard `alpinejs` package uses `new Function()` for expression evaluation, and the `@alpinejs/csp` package replaces expression evaluation with a compiled set of allowed directives. The CSP build cannot parse arbitrary JavaScript expressions in HTML attributes — instead you define named functions on `window.Alpine.magic` or register components via `Alpine.data()` in an external script. Cloudflare Pages `_headers` files are deployed as part of the static asset bundle and processed by the CDN before the browser receives a response, making them the right place to set `Content-Security-Policy` without a Worker. The `nonce` approach is an alternative but requires per-request generation, which means a Worker or Pages Function.

## Cloudflare Pages `_headers` File

```
# public/_headers
/*
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://cdn.example.com; connect-src 'self' https://api.example.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()

/api/*
  Cache-Control: no-store
```

## Installing the CSP-Compatible Alpine Build

```html
<!-- index.html — load the CSP build instead of the standard build -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>My App</title>
    <link rel="stylesheet"  />
  </head>
  <body>
    <!-- Alpine components are registered in alpine-init.js, not inline -->
    <div x-data="counter">
      <p>Count: <span x-text="count"></span></p>
      <button x-on:click="increment">Increment</button>
      <button x-on:click="decrement" x-bind:disabled="count <= 0">
        Decrement
      </button>
    </div>

    <!-- Only an external script reference — no inline JS, no eval needed -->
    <script  defer></script>
    <script  defer></script>
  </body>
</html>
```

## Registering Components via `Alpine.data()`

```typescript
// src/alpine-init.ts  (bundled to /alpine-init.js by Vite)
import type { AlpineComponent } from "alpinejs";

// Augment the global Alpine instance provided by the CSP CDN build
declare global {
  interface Window {
    Alpine: {
      data(name: string, factory: () => AlpineComponent): void;
      magic(name: string, fn: (el: Element) => unknown): void;
      start(): void;
    };
  }
}

// All logic lives in typed JS — no Function() evaluation at runtime
document.addEventListener("alpine:init", () => {
  window.Alpine.data("counter", () => ({
    count: 0 as number,

    increment() {
      this.count++;
    },

    decrement() {
      if (this.count > 0) this.count--;
    },
  }));

  window.Alpine.data("productSearch", () => ({
    query: "" as string,
    results: [] as Array<{ id: string; name: string; price: number }>,
    loading: false as boolean,
    error: "" as string,

    async search() {
      if (this.query.trim().length < 2) return;

      this.loading = true;
      this.error = "";

      try {
        const res = await fetch(
          `/api/search?q=${encodeURIComponent(this.query)}`
        );

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        this.results = await res.json();
      } catch (err) {
        this.error = err instanceof Error ? err.message : "Search failed";
        this.results = [];
      } finally {
        this.loading = false;
      }
    },
  }));
});
```

## Product Search Component in HTML

```html
<!-- products.html -->
<section x-data="productSearch" class="p-6">
  <label class="block mb-2 font-semibold" for="search">Search products</label>
  <input
    id="search"
    type="search"
    x-model="query"
    x-on:input.debounce.300ms="search"
    placeholder="Type at least 2 characters…"
    class="w-full rounded border px-3 py-2"
  />

  <p
    x-show="loading"
    class="mt-4 animate-pulse text-gray-500"
    x-cloak
  >
    Searching…
  </p>

  <p
    x-show="error"
    x-text="error"
    class="mt-4 text-red-600"
    x-cloak
  ></p>

  <ul
    x-show="results.length > 0 && !loading"
    class="mt-4 divide-y rounded border"
    x-cloak
  >
    <template x-for="product in results" :key="product.id">
      <li class="flex items-center justify-between px-4 py-3">
        <span x-text="product.name" class="font-medium"></span>
        <span
          x-text="new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(product.price)"
          class="tabular-nums text-gray-600"
        ></span>
      </li>
    </template>
  </ul>
</section>
```

## Pages Function Search Endpoint

```typescript
// functions/api/search.ts  (Cloudflare Pages Function)
interface Env {
  PRODUCTS_KV: KVNamespace;
}

interface Product {
  id: string;
  name: string;
  price: number;
}

export const onRequestGet: PagesFunction<Env> = async ({ request, env }) => {
  const url = new URL(request.url);
  const query = (url.searchParams.get("q") ?? "").trim().toLowerCase();

  if (query.length < 2) {
    return Response.json({ error: "Query too short" }, { status: 400 });
  }

  const allProducts =
    (await env.PRODUCTS_KV.get<Product[]>("products:all", { type: "json" })) ??
    [];

  const results = allProducts
    .filter((p) => p.name.toLowerCase().includes(query))
    .slice(0, 20);

  return Response.json(results, {
    headers: {
      "Cache-Control": "no-store",
      // The CSP on /* already covers this; explicit here for the API route
      "Content-Type": "application/json",
    },
  });
};
```

## Anti-patterns

- Using the standard `alpinejs` CDN build with a `script-src 'self'` CSP — every `x-on` and `x-bind` expression will throw a `EvalError` and Alpine will silently stop working.
- Adding `'unsafe-eval'` to relax the CSP instead of switching to the CSP build — this undermines the entire policy and opens the app to XSS attacks that can exfiltrate data via `eval`.
- Putting Alpine component logic in inline `<script>` tags — they require `'unsafe-inline'` in `script-src`, which also voids most of the CSP's XSS protection.

## Gotchas

- The `@alpinejs/csp` build does not support `x-on:click="count++"` style inline expressions; expressions must resolve to a method name registered via `Alpine.data()`. Attempting to use an arithmetic expression in HTML silently no-ops.
- `x-cloak` requires a companion CSS rule (`[x-cloak] { display: none; }`) in a stylesheet loaded before Alpine initialises; without it, un-hydrated templates flash before Alpine hides them.

## Verification

```bash
# Deploy to Cloudflare Pages and check CSP is applied
curl -sI https://your-project.pages.dev | grep -i content-security-policy

# Validate _headers syntax locally
npx wrangler pages dev public --compatibility-date=2025-01-01

# Confirm no eval calls in the CSP bundle
grep -i "new Function\|eval(" node_modules/@alpinejs/csp/dist/cdn.min.js
```

## Related

- `frontend/cloudflare-pages-headers-csp-mobile.md`
- `frontend/pwa-service-worker-cloudflare-pages.md`
- `frontend/feature-flags-cloudflare-workers-kv-edge-config.md`

## Sources

- https://alpinejs.dev/advanced/csp
- https://developers.cloudflare.com/pages/configuration/headers/
- https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP
