# Edge Personalisation with HTMLRewriter in Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You serve a single static HTML page from R2 or Workers Assets but need different users to see different content — a "Welcome back, Pro member" banner vs. a trial CTA, regional pricing, or A/B copy variants — without a round-trip to an application server and without shipping a large JS personalisation library to the browser.

## Context

CDN-level personalisation historically required Varnish ESI or a Lambda@Edge function. Cloudflare Workers gives you a scriptable, zero-cold-start layer at the edge with:

- **KV** — low-latency key/value store holding user segment data and A/B variant assignments.
- **HTMLRewriter** — a streaming SAX-like transformer that rewrites response HTML without buffering it into memory.
- **Cookie parsing** — first-class in the `Request` headers; no library needed.

Personalisation happens during the streaming pipeline, so Time To First Byte is almost unchanged.

## Solution

### 1. Segment detection from KV + cookie

```typescript
// worker/personalise.ts
import { Env } from './types';

export type Segment = 'trial' | 'pro' | 'enterprise' | 'anonymous';

export async function detectSegment(
  request: Request,
  env: Env
): Promise<Segment> {
  const cookieHeader = request.headers.get('Cookie') ?? '';
  const userId = parseCookie(cookieHeader, 'uid');

  if (!userId) return 'anonymous';

  // KV key format: "segment:{userId}"
  const segment = await env.KV.get<Segment>(`segment:${userId}`, 'text');
  return segment ?? 'anonymous';
}

function parseCookie(header: string, name: string): string | null {
  const prefix = `${name}=`;
  for (const part of header.split(';')) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length));
    }
  }
  return null;
}
```

### 2. A/B variant assignment

```typescript
// worker/ab.ts
import { Env } from './types';

export type Variant = 'control' | 'variant-a' | 'variant-b';

const VARIANTS: Variant[] = ['control', 'variant-a', 'variant-b'];
const WEIGHTS  = [0.5, 0.25, 0.25]; // 50 / 25 / 25 split

export async function assignVariant(
  userId: string,
  experimentId: string,
  env: Env
): Promise<Variant> {
  const kvKey = `ab:${experimentId}:${userId}`;

  // Sticky assignment: once set, always the same variant
  const existing = await env.KV.get<Variant>(kvKey, 'text');
  if (existing) return existing;

  // Deterministic pseudo-random bucket from user+experiment hash
  const hash = await sha256(`${experimentId}:${userId}`);
  const bucket = (hash[0] / 255); // 0..1

  let cumulative = 0;
  let chosen: Variant = 'control';
  for (let i = 0; i < VARIANTS.length; i++) {
    cumulative += WEIGHTS[i];
    if (bucket < cumulative) { chosen = VARIANTS[i]; break; }
  }

  // Persist for 30 days
  await env.KV.put(kvKey, chosen, { expirationTtl: 60 * 60 * 24 * 30 });
  return chosen;
}

async function sha256(input: string): Promise<Uint8Array> {
  const encoded = new TextEncoder().encode(input);
  const buf = await crypto.subtle.digest('SHA-256', encoded);
  return new Uint8Array(buf);
}
```

### 3. HTMLRewriter element handlers

```typescript
// worker/handlers.ts
import { Segment } from './personalise';
import { Variant } from './ab';

/** Replace [data-slot] placeholders with personalised HTML */
export class SlotHandler implements HTMLRewriterElementContentHandlers {
  constructor(
    private readonly segment: Segment,
    private readonly variant: Variant
  ) {}

  element(el: Element) {
    const slot = el.getAttribute('data-slot');
    if (!slot) return;

    const content = this.resolveSlot(slot);
    if (content !== null) {
      el.setInnerContent(content, { html: true });
    }
  }

  private resolveSlot(slot: string): string | null {
    switch (slot) {
      case 'cta-banner':
        return this.ctaBanner();
      case 'pricing-table':
        return this.pricingTable();
      default:
        return null;
    }
  }

  private ctaBanner(): string {
    if (this.segment === 'pro' || this.segment === 'enterprise') {
      return '<p class="banner banner--pro">Welcome back, Pro member! <a >Go to Dashboard</a></p>';
    }
    if (this.variant === 'variant-a') {
      return '<p class="banner banner--trial">Start your free trial — no credit card needed.</p>';
    }
    return '<p class="banner banner--default">Upgrade today and save 20%.</p>';
  }

  private pricingTable(): string {
    const highlight = this.segment === 'enterprise' ? 'enterprise' : 'pro';
    return `<div class="pricing" data-highlight="${highlight}"><!-- pricing rows --></div>`;
  }
}

/** Rewrite <meta> tags for personalised SEO/OG */
export class MetaHandler implements HTMLRewriterElementContentHandlers {
  constructor(private readonly segment: Segment) {}

  element(el: Element) {
    const name = el.getAttribute('name') ?? el.getAttribute('property') ?? '';
    if (name === 'og:description' && this.segment === 'enterprise') {
      el.setAttribute(
        'content',
        'Enterprise-grade features, SSO, and dedicated support.'
      );
    }
  }
}
```

### 4. Main Worker entry point

```typescript
// worker/index.ts
import { Env } from './types';
import { detectSegment } from './personalise';
import { assignVariant } from './ab';
import { SlotHandler, MetaHandler } from './handlers';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // 1. Resolve user context
    const segment = await detectSegment(request, env);
    const userId  = request.headers.get('Cookie')?.match(/uid=([^;]+)/)?.[1] ?? 'anon';
    const variant = await assignVariant(userId, 'homepage-cta-q3', env);

    // 2. Fetch the static HTML shell (no-store for personalised; cache hit for static)
    const assetUrl = new URL('/index.html', `https://${env.ASSETS_HOST}`);
    const upstream = await fetch(assetUrl, {
      // Always bypass CDN cache for personalised responses
      cf: { cacheEverything: false },
    });

    if (!upstream.ok) return upstream;

    // 3. Stream through HTMLRewriter
    const transformed = new HTMLRewriter()
      .on('[data-slot]',      new SlotHandler(segment, variant))
      .on('meta[name], meta[property]', new MetaHandler(segment))
      .transform(upstream);

    // 4. Annotate the response so downstream caches don't store it
    const response = new Response(transformed.body, transformed);
    response.headers.set('Cache-Control', 'private, no-store');
    response.headers.set('Vary', 'Cookie');
    // Expose segment + variant for analytics (stripped by HTMLRewriter before client)
    response.headers.set('X-Segment', segment);
    response.headers.set('X-Variant', variant);

    return response;
  },
};
```

### 5. Types

```typescript
// worker/types.ts
export interface Env {
  KV: KVNamespace;
  ASSETS_HOST: string;
}
```

### 6. HTML slot placeholders

```html
<!-- public/index.html -->
<head>
  <meta name="og:description" content="Default description for social sharing.">
</head>
<body>
  <!-- Personalised slot — replaced at the edge -->
  <div data-slot="cta-banner">
    <!-- Fallback content rendered if Worker fails or JS is off -->
    <p>Try our product today.</p>
  </div>

  <section data-slot="pricing-table">
    <!-- Static pricing fallback -->
  </section>
</body>
```

## Implementation Details

- **KV read latency** on Cloudflare's edge is typically < 5 ms for recently-written keys (served from a regional replica). For truly latency-sensitive paths, consider embedding the segment in the JWT/cookie itself so the Worker reads zero KV.
- **HTMLRewriter is streaming** — the first bytes reach the browser before the Worker has finished reading the upstream response. Keep handlers stateless and fast.
- **`Vary: Cookie`** ensures intermediate caches (Cloudflare's own cache, CDN PoPs) do not serve a personalised response to another user. Combined with `Cache-Control: private, no-store`, the personalised response is never stored.
- **Fallback content** inside `[data-slot]` is visible if the Worker errors or the handler returns `null`. Always put meaningful static content there.
- **A/B sticky assignment** is essential for consistent UX: use KV to persist the variant keyed by user ID, not a random per-request roll.

## Anti-patterns

- **Caching personalised HTML at the CDN level** — will serve one user's personalised content to another. Always set `Cache-Control: private` or `no-store`.
- **Doing personalisation in client JS** — causes layout shift (CLS) and exposes segment logic to end users. Do it at the edge.
- **Reading the full response body into memory** (`await response.text()`) before running HTMLRewriter — destroys the streaming benefit and can OOM on large pages.
- **Storing PII in KV values** — store only opaque segment identifiers (`pro`, `trial`), never email addresses or names.

## Gotchas

- `el.setInnerContent(html, { html: true })` — the second argument is mandatory to parse the string as HTML rather than text. Omitting it escapes angle brackets.
- HTMLRewriter selectors do not support pseudo-classes (`:first-child`, `:not()`). Use attribute selectors and class names.
- KV `get()` returns `null` for missing keys, not `undefined`. Always handle the `null` case.
- `Vary: Cookie` causes Cloudflare to treat every unique Cookie header as a separate cache key, effectively disabling caching for logged-in users — which is usually the desired behaviour for personalised routes.

## Verification

1. `wrangler dev` with a `uid` cookie set to a KV-enrolled user — confirm the slot content changes.
2. Curl without a cookie — confirm the fallback/anonymous content is returned.
3. Check `response.headers.get('X-Variant')` in DevTools for the assigned variant.
4. Lighthouse / WebPageTest — verify TTFB is within ~10 ms of the non-personalised baseline.
5. Run an A/B split check: generate 1000 random user IDs, compute variants, confirm ~50/25/25 distribution.

## Related

- `workers-islands-architecture-partial-hydration.md` — streaming HTML shell that hosts personalised slots
- `workers-dark-mode-cookie-edge.md` — another edge HTML mutation use-case
- `workers-static-form-handler-d1.md` — handling form submissions that update the user's segment

## Sources

- Cloudflare HTMLRewriter API: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Cloudflare KV API: https://developers.cloudflare.com/kv/api/
- Cloudflare Cache behaviour with Vary: https://developers.cloudflare.com/cache/concepts/cache-keys/
