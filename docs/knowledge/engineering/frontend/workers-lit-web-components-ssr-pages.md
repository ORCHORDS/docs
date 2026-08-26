# Lit Web Components SSR on Cloudflare Pages

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a component library built with Lit and want first-paint HTML delivered
from the edge — no blank page flash, no layout shift — while still keeping
full client-side interactivity after hydration. Cloudflare Pages Functions let
you run `@lit-labs/ssr` inside the same deployment as your static assets.

## Context

- **Lit 3 / @lit-labs/ssr 1.x** — declarative shadow DOM (DSD) polyfill no
  longer required in Chrome 90+, Firefox 123+, Safari 16.4+
- **Pages Functions** run on the Workers runtime (V8 isolate, no Node built-ins
  by default)
- `renderToReadableStream` returns a `ReadableStream<string>` compatible with
  the Fetch API's `Response` body
- Hydration is handled automatically by Lit's `LitElement` client bundle: the
  element re-connects to the existing shadow root instead of re-rendering

---

## 1 — Install dependencies

```bash
npm install lit @lit-labs/ssr
# peer dep — generates <template shadowrootmode="open"> markup
npm install @webcomponents/template-shadowroot
```

Ensure your `tsconfig.json` targets `ES2020` or later and enables
`"useDefineForClassFields": false` (required by Lit decorators).

## 2 — Define the component (shared between SSR and client)

```typescript
// src/components/hero-banner.ts
import { LitElement, html, css } from 'lit';
import { customElement, property } from 'lit/decorators.js';

@customElement('hero-banner')
export class HeroBanner extends LitElement {
  static styles = css`
    :host {
      display: block;
      padding: 2rem;
      background: var(--brand, #0066cc);
      color: #fff;
      border-radius: 8px;
    }
    h1 { margin: 0 0 0.5rem; font-size: 2rem; }
    p  { margin: 0; opacity: 0.85; }
  `;

  @property() heading = 'Hello from the edge';
  @property() subtext = '';

  render() {
    return html`
      <h1>${this.heading}</h1>
      ${this.subtext ? html`<p>${this.subtext}</p>` : ''}
    `;
  }
}
```

## 3 — Pages Function that streams SSR output

```typescript
// functions/index.ts  (maps to GET /)
import { render } from '@lit-labs/ssr';
import { html } from 'lit';
import { HeroBanner } from '../src/components/hero-banner.js';

// Register element on the SSR side (Workers global)
void HeroBanner;

export const onRequestGet: PagesFunction = async (ctx) => {
  const heading = new URL(ctx.request.url).searchParams.get('h') ?? 'Cloudflare Edge';

  // renderToReadableStream is the streaming variant
  const { renderToReadableStream } = await import('@lit-labs/ssr/lib/render-to-readable-stream.js');

  const ssrStream = renderToReadableStream(html`
    <hero-banner heading=${heading} subtext="Rendered at the edge"></hero-banner>
  `);

  // Wrap inside a full HTML document
  const prefix = new TextEncoder().encode(
    `<!doctype html><html lang="en"><head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>${heading}</title>
      <script type="module" ></script>
    </head><body>`
  );
  const suffix = new TextEncoder().encode('</body></html>');

  const body = concatStreams([
    toStream(prefix),
    ssrStream as unknown as ReadableStream<Uint8Array>,
    toStream(suffix),
  ]);

  return new Response(body, {
    headers: {
      'content-type': 'text/html; charset=utf-8',
      'transfer-encoding': 'chunked',
    },
  });
};

// Utilities ──────────────────────────────────────────────────────────────────

function toStream(chunk: Uint8Array): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(ctrl) {
      ctrl.enqueue(chunk);
      ctrl.close();
    },
  });
}

function concatStreams(streams: ReadableStream<Uint8Array>[]): ReadableStream<Uint8Array> {
  let i = 0;
  const iter = () => streams[i]?.getReader();
  let reader = iter();
  return new ReadableStream({
    async pull(ctrl) {
      if (!reader) { ctrl.close(); return; }
      const { done, value } = await reader.read();
      if (done) {
        reader.releaseLock();
        i++;
        reader = iter();
        return;
      }
      ctrl.enqueue(value);
    },
  });
}
```

## 4 — Client-side hydration bundle

```typescript
// public/client.ts  (bundled → public/client.js)
// Importing the element registers it; Lit hydrates any DSD roots automatically.
import '../src/components/hero-banner.js';
```

Build with:
```bash
npx esbuild public/client.ts --bundle --format=esm --outfile=public/client.js
```

## Anti-patterns

- **Calling `document` or `window` inside component constructors** — SSR runs in
  a Workers isolate; `document` is `undefined`. Gate DOM access behind
  `connectedCallback` or lifecycle hooks.
- **Importing Node-only packages** (`fs`, `path`) inside components consumed by
  SSR — use the `browser` field in `package.json` to alias them.
- **Not tree-shaking the SSR package into the client bundle** — `@lit-labs/ssr`
  must never ship to the browser; keep SSR imports in Functions-only files.

## Gotchas

1. **Compatibility flags** — Add `nodejs_compat` to `wrangler.toml` only if a
   transitive dep requires it; it adds ~2 ms cold-start overhead.
2. **`renderToReadableStream` vs `render`** — `render()` returns a sync
   generator and blocks the event loop; always prefer the stream variant in
   production Workers.
3. **DSD polyfill** — Safari < 16.4 needs the
   `@webcomponents/template-shadowroot` polyfill loaded before the element
   script. Feature-detect with `HTMLTemplateElement.prototype.hasOwnProperty('shadowRootMode')`.
4. **Attribute reflection** — SSR renders attribute values only; complex objects
   passed as properties need serialisation (JSON in a hidden `<script>` tag) and
   re-hydration in `connectedCallback`.

## Verification

```bash
# Start Pages dev server
npx wrangler pages dev public --compatibility-date=2025-01-01

# Verify DSD markup is present in the raw HTML (no JS needed)
curl -s http://localhost:8788/ | grep 'shadowrootmode'
# Expected: <template shadowrootmode="open">...

# Lighthouse score (should show FCP improvement vs CSR baseline)
npx lighthouse http://localhost:8788/ --only-categories=performance --output=json \
  | jq '.categories.performance.score'
```

## Related

- `documentation/docs/policies/frontend/workers-preact-islands-architecture.md`
- `documentation/workers/workers-streaming-html-response.md`
- `documentation/cloudflare-pages/pages-functions-routing.md`

## Sources

- https://lit.dev/docs/ssr/overview/
- https://developers.cloudflare.com/pages/functions/
- https://web.dev/declarative-shadow-dom/
