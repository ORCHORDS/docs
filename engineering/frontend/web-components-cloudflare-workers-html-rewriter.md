# Web Components with Cloudflare Workers HTML Rewriter

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You serve a mostly-static HTML site through Cloudflare Pages / Workers and want to inject
personalised content (user name, cart count, feature flags, geo-targeted banners) into
Web Components without a full SSR framework. Cloudflare Workers' `HTMLRewriter` lets you
stream-transform the HTML response at the edge — rewriting custom element attributes and
slots before the first byte reaches the browser — so the Web Components mount with
server-supplied data already in the DOM, avoiding a client-side fetch flicker.

---

## Context

`HTMLRewriter` is a streaming HTML parser and transformer built into the Cloudflare Workers
runtime. It works like a SAX parser: you attach handlers to CSS selectors and mutate
matching elements as they stream through the Worker. It is not available in browsers.

Web Components (custom elements + Shadow DOM) are a natural pairing: the component's
upgrade logic runs in the browser after the Worker has already patched attribute values and
slot content. This avoids JavaScript frameworks for simple personalisation use cases.

Architecture:
```
Browser → Cloudflare Pages (static HTML) → Worker (HTMLRewriter) → Browser
                                              ↓ reads KV / D1 for user data
```

The static HTML contains Web Components with placeholder attributes. The Worker patches those
attributes on the fly based on the authenticated session.

---

## Section 1 — Defining the Web Components

Write components that read their data from attributes (set by the Worker) and from slotted
children:

```js
// public/components/user-greeting.js
class UserGreeting extends HTMLElement {
  static observedAttributes = ['user-name', 'avatar-url'];

  connectedCallback() {
    this.#render();
  }

  attributeChangedCallback() {
    if (this.isConnected) this.#render();
  }

  #render() {
    const name = this.getAttribute('user-name') ?? 'there';
    const avatar = this.getAttribute('avatar-url');
    // Use declarative shadow DOM if SSR-hydration is needed; else open shadow
    if (!this.shadowRoot) {
      this.attachShadow({ mode: 'open' });
    }
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: clamp(0.875rem, 2.5vw, 1rem);
        }
        img {
          width: 2rem;
          height: 2rem;
          border-radius: 50%;
          object-fit: cover;
        }
        span { font-weight: 600; }
      </style>
      ${avatar ? `<img  alt="${name}'s avatar" loading="lazy">` : ''}
      <span>Hello, ${name}!</span>
    `;
  }
}

customElements.define('user-greeting', UserGreeting);
```

```js
// public/components/cart-badge-wc.js
class CartBadge extends HTMLElement {
  static observedAttributes = ['count'];

  connectedCallback() { this.#render(); }
  attributeChangedCallback() { if (this.isConnected) this.#render(); }

  #render() {
    const count = parseInt(this.getAttribute('count') ?? '0', 10);
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `
      <style>
        :host { position: relative; display: inline-block; }
        .badge {
          position: absolute;
          top: -6px; right: -6px;
          min-width: 18px; height: 18px;
          border-radius: 9px;
          background: #e53e3e;
          color: #fff;
          font-size: 11px;
          line-height: 18px;
          text-align: center;
          padding: 0 4px;
          /* Ensure badge doesn't obscure the host's 44px tap target */
          pointer-events: none;
        }
        .badge[hidden] { display: none; }
      </style>
      <slot></slot>
      <span class="badge" ?hidden="${count === 0}" aria-label="${count} items in cart">
        ${count > 0 ? count : ''}
      </span>
    `;
  }
}

customElements.define('cart-badge', CartBadge);
```

Include these scripts in the static HTML with `type="module"`:

```html
<!-- public/index.html (fragment) -->
<script type="module" ></script>
<script type="module" ></script>

<header>
  <!-- Worker will patch user-name and avatar-url -->
  <user-greeting user-name="Guest" avatar-url=""></user-greeting>

  <nav>
    <!-- Worker will patch count attribute -->
    <cart-badge count="0">
      <a  aria-label="Cart">🛒</a>
    </cart-badge>
  </nav>
</header>
```

---

## Section 2 — HTMLRewriter Worker to Patch Attributes

```ts
// worker/src/index.ts
import type { KVNamespace } from '@cloudflare/workers-types';

interface Env {
  SESSIONS: KVNamespace;       // session_id → JSON(UserSession)
  STATIC_ASSETS: Fetcher;      // Pages asset binding
}

interface UserSession {
  userId: string;
  name: string;
  avatarUrl: string;
  cartCount: number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Only intercept HTML pages — let JS, CSS, images pass through
    const url = new URL(request.url);
    const accept = request.headers.get('Accept') ?? '';
    const isHtmlRequest =
      accept.includes('text/html') ||
      url.pathname === '/' ||
      url.pathname.endsWith('.html');

    if (!isHtmlRequest) {
      return env.STATIC_ASSETS.fetch(request);
    }

    // Fetch the static HTML from Pages
    const response = await env.STATIC_ASSETS.fetch(request);

    // Not a successful HTML page — return as-is (404, 301, etc.)
    if (!response.ok || !response.headers.get('Content-Type')?.includes('text/html')) {
      return response;
    }

    // Resolve user session from cookie
    const session = await resolveSession(request, env);

    // Stream-transform with HTMLRewriter
    return new HTMLRewriter()
      .on('user-greeting', new UserGreetingHandler(session))
      .on('cart-badge', new CartBadgeHandler(session))
      .on('head', new PerformanceHintHandler())
      .transform(response);
  },
};

async function resolveSession(
  request: Request,
  env: Env
): Promise<UserSession | null> {
  const cookie = request.headers.get('Cookie') ?? '';
  const match = cookie.match(/session=([^;]+)/);
  if (!match) return null;

  try {
    const raw = await env.SESSIONS.get(match[1], 'text');
    return raw ? (JSON.parse(raw) as UserSession) : null;
  } catch {
    return null;
  }
}

class UserGreetingHandler implements ElementHandler {
  constructor(private session: UserSession | null) {}

  element(el: Element) {
    if (!this.session) return; // leave placeholder attributes for guests
    el.setAttribute('user-name', this.session.name);
    el.setAttribute('avatar-url', this.session.avatarUrl);
  }
}

class CartBadgeHandler implements ElementHandler {
  constructor(private session: UserSession | null) {}

  element(el: Element) {
    const count = this.session?.cartCount ?? 0;
    el.setAttribute('count', String(count));
  }
}

class PerformanceHintHandler implements ElementHandler {
  element(el: Element) {
    // Inject modulepreload for Web Component scripts to reduce parse delay
    el.prepend(
      `<link rel="modulepreload" >` +
      `<link rel="modulepreload" >`,
      { html: true }
    );
  }
}
```

---

## Section 3 — Declarative Shadow DOM for Instant First Paint

Without Declarative Shadow DOM (DSD), the Web Component renders its shadow on script
execution, which is after HTML parsing. Users see the placeholder content briefly. With DSD
the shadow is part of the HTML stream — the Worker can inject it.

```ts
// Advanced: inject DSD template for user-greeting
class UserGreetingDSDHandler implements ElementHandler {
  constructor(private session: UserSession | null) {}

  element(el: Element) {
    const name = this.session?.name ?? 'Guest';
    const avatar = this.session?.avatarUrl ?? '';

    el.setAttribute('user-name', name);
    el.setAttribute('avatar-url', avatar);

    // Inject Declarative Shadow DOM so the component renders before JS runs
    el.setInnerContent(
      `<template shadowrootmode="open">
        <style>
          :host { display: flex; align-items: center; gap: .5rem;
                  font-size: clamp(.875rem, 2.5vw, 1rem); }
          img { width: 2rem; height: 2rem; border-radius: 50%; object-fit: cover; }
          span { font-weight: 600; }
        </style>
        ${avatar ? `<img  alt="${name}'s avatar" loading="lazy">` : ''}
        <span>Hello, ${name}!</span>
      </template>`,
      { html: true }
    );
  }
}
```

The client-side `UserGreeting` class then uses `this.shadowRoot` (already present from DSD)
instead of calling `attachShadow`, preventing a double-render.

---

## Section 4 — Feature Flags and Geo-Targeted Content

HTMLRewriter can conditionally show/hide entire components based on CF geo headers:

```ts
class FeatureFlagHandler implements ElementHandler {
  constructor(
    private enabledFeatures: Set<string>,
    private country: string
  ) {}

  element(el: Element) {
    const feature = el.getAttribute('data-feature');
    const geoTarget = el.getAttribute('data-geo');

    const featureEnabled = feature ? this.enabledFeatures.has(feature) : true;
    const geoMatch = geoTarget ? geoTarget.split(',').includes(this.country) : true;

    if (!featureEnabled || !geoMatch) {
      el.remove(); // strip the element from the stream entirely
    } else {
      // Remove the data attributes so they don't appear in the rendered DOM
      el.removeAttribute('data-feature');
      el.removeAttribute('data-geo');
    }
  }
}

// In the main fetch handler:
const country = request.cf?.country ?? 'US';
const features = await resolveFeatureFlags(env, session);

new HTMLRewriter()
  .on('[data-feature],[data-geo]', new FeatureFlagHandler(features, country))
  .transform(response);
```

Usage in HTML:

```html
<!-- Only shown in DE, AT, CH and only when 'vat-display' flag is enabled -->
<div data-feature="vat-display" data-geo="DE,AT,CH">
  Incl. 19% VAT
</div>
```

---

## Anti-patterns

- **Putting secrets in attribute values** — HTMLRewriter output is the raw HTML stream.
  Never patch an attribute with a session token or private user ID; use opaque references
  (display names only, not internal IDs).
- **Using `el.innerHTML` (which doesn't exist on HTMLRewriter's `Element`)** — use
  `el.setInnerContent(str, { html: true })` instead.
- **Transforming all requests** — `HTMLRewriter` adds ~1–5 ms CPU per kilobyte of HTML.
  Gate it to `Accept: text/html` requests only; never run it on JSON, images, or JS.
- **Relying on HTMLRewriter for client-side reactivity** — it runs once at the edge during
  the initial request. For real-time updates (live cart count, WebSocket messages), use
  client-side Web Component logic after initial paint.
- **Forgetting Content-Security-Policy with inline styles** — DSD templates injected by
  the Worker contain `<style>` tags. If your CSP has `style-src 'self'` without
  `'unsafe-inline'`, the shadow styles will be blocked. Use a nonce or hash; the Worker can
  inject the nonce into both the CSP header and the injected template.

---

## Gotchas

- `HTMLRewriter` is synchronous within a streaming transform but the outer handler (`fetch`)
  can be async. You must resolve all async data (KV lookups, D1 queries) **before** calling
  `.transform(response)` — element handlers cannot be `async`.
- The `element()` method on `ElementHandler` receives the element as it streams. You cannot
  look ahead in the stream from an element handler.
- Declarative Shadow DOM (`shadowrootmode`) requires Chrome 111+, Safari 16.4+, Firefox 123+.
  Provide a polyfill or ensure the custom element's `connectedCallback` gracefully handles the
  case where `this.shadowRoot` is already populated (don't call `attachShadow` again).
- `customElements.define` throws if the same tag is registered twice. Use `customElements.get`
  before defining in scripts that may be loaded multiple times:

  ```js
  if (!customElements.get('user-greeting')) {
    customElements.define('user-greeting', UserGreeting);
  }
  ```

- HTMLRewriter on Cloudflare Pages requires the Worker to be deployed as a **Pages Function**
  (in `/functions/`) or as a Worker that proxies the Pages static assets via a `STATIC_ASSETS`
  binding, not as a standalone Worker on a different route.

---

## Verification

1. Deploy the Worker with a test session in KV (`wrangler kv:key put --binding SESSIONS "test-session-id" '{"name":"Alice","avatarUrl":"/alice.jpg","cartCount":3}'`).
2. Request the page with `curl -H "Cookie: session=test-session-id" https://yoursite.pages.dev/ | grep user-greeting`. Should see `user-name="Alice"` in the HTML stream.
3. In the browser with a real session cookie, inspect the `<user-greeting>` element in DevTools — `user-name` attribute should already be set when `DOMContentLoaded` fires (before JS upgrade).
4. Disable JavaScript in DevTools. The DSD variant should still show the greeting (CSS-only render from the injected template).
5. Throttle to "Slow 4G". Confirm the greeting text appears before the first `user-greeting.js` script is executed (visible in the Performance timeline).

---

## Related

- `web-components-custom-elements.md`
- `web-components-shadow-dom-patterns.md`
- `declarative-shadow-dom-serialization-and-cloning.md`
- `next-js-middleware-patterns.md`
- `cloudflare-pages-headers-csp-mobile.md`

---

## Sources

- Cloudflare HTMLRewriter docs: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Declarative Shadow DOM: https://developer.chrome.com/docs/css-ui/declarative-shadow-dom
- MDN Custom Elements: https://developer.mozilla.org/en-US/docs/Web/API/Web_components/Using_custom_elements
- Web Components best practices: https://web.dev/articles/web-components-best-practices
- Cloudflare Pages Functions: https://developers.cloudflare.com/pages/functions/
