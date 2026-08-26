# Web Components with Shadow DOM Consuming a Cloudflare Workers JSON API

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You are building a framework-agnostic widget library using Web Components with shadow DOM. The components fetch data from a Cloudflare Workers JSON API, but you run into two recurring issues: `credentials:'include'` CORS requests are blocked by the Workers default policy, and the Cloudflare Turnstile widget script cannot inject its iframe into a closed shadow root. You also want server-side rendering support via declarative shadow DOM so that Pages-hosted components render without a layout shift on first paint.

## Context

Shadow DOM encapsulates styles and DOM subtrees, but it also creates isolation problems: external scripts (like Turnstile) that manipulate `document.body` cannot reach inside a shadow root, and CORS preflight requests from a custom element on one origin to a Workers API on another require explicit `Access-Control-Allow-Credentials` headers. Declarative shadow DOM (`<template shadowrootmode="open">`) allows Pages to serve pre-rendered shadow trees in HTML that the browser hydrates without JavaScript. Custom element lifecycle callbacks (`connectedCallback`, `disconnectedCallback`, `attributeChangedCallback`) provide the equivalent of React's `useEffect` and `useMemo` without a framework dependency.

## Custom Element Lifecycle and Shadow DOM Setup

```typescript
// src/elements/post-card.ts

const TEMPLATE = document.createElement('template');
TEMPLATE.innerHTML = `
  <style>
    :host {
      display: block;
      border: 1px solid var(--border-color, #e2e8f0);
      border-radius: 8px;
      padding: 1rem;
      font-family: inherit;
    }
    .title { font-size: 1.125rem; font-weight: 600; margin: 0 0 .5rem; }
    .body  { font-size: .875rem; color: var(--text-muted, #64748b); }
    .error { color: #ef4444; font-size: .875rem; }
    .skeleton {
      background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
      background-size: 200% 100%;
      animation: shimmer 1.4s infinite;
      border-radius: 4px;
      height: 1em;
      margin-bottom: .5rem;
    }
    @keyframes shimmer { to { background-position: -200% 0; } }
  </style>
  <div class="title"></div>
  <div class="body"></div>
  <div class="error" hidden></div>
`;

export class PostCard extends HTMLElement {
  static observedAttributes = ['post-id', 'api-base'];

  private shadow: ShadowRoot;
  private abortController: AbortController | null = null;

  constructor() {
    super();
    this.shadow = this.attachShadow({ mode: 'open' });
    this.shadow.appendChild(TEMPLATE.content.cloneNode(true));
  }

  connectedCallback(): void {
    this.fetchPost();
  }

  disconnectedCallback(): void {
    this.abortController?.abort();
  }

  attributeChangedCallback(
    name: string, _old: string | null, next: string | null
  ): void {
    if (next !== null) this.fetchPost();
  }

  private async fetchPost(): Promise<void> {
    const postId = this.getAttribute('post-id');
    const apiBase = this.getAttribute('api-base') ?? '/api';
    if (!postId) return;

    this.abortController?.abort();
    this.abortController = new AbortController();
    this.setLoading();

    try {
      const res = await fetch(`${apiBase}/posts/${postId}`, {
        credentials: 'include',
        signal: this.abortController.signal,
        headers: { accept: 'application/json' },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const post = await res.json() as { title: string; body: string };
      this.render(post);
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      this.showError((err as Error).message);
    }
  }

  private setLoading(): void {
    const title = this.shadow.querySelector<HTMLElement>('.title')!;
    const body  = this.shadow.querySelector<HTMLElement>('.body')!;
    title.className = 'skeleton';
    body.className  = 'skeleton';
    title.textContent = '';
    body.textContent  = '';
  }

  private render(post: { title: string; body: string }): void {
    this.shadow.querySelector<HTMLElement>('.title')!.className = 'title';
    this.shadow.querySelector<HTMLElement>('.body')!.className  = 'body';
    this.shadow.querySelector<HTMLElement>('.title')!.textContent = post.title;
    this.shadow.querySelector<HTMLElement>('.body')!.textContent  = post.body;
    this.shadow.querySelector<HTMLElement>('.error')!.hidden = true;
  }

  private showError(msg: string): void {
    this.shadow.querySelector<HTMLElement>('.title')!.textContent = '';
    this.shadow.querySelector<HTMLElement>('.body')!.textContent  = '';
    const err = this.shadow.querySelector<HTMLElement>('.error')!;
    err.textContent = `Error: ${msg}`;
    err.hidden = false;
  }
}

customElements.define('post-card', PostCard);
```

## Workers API with CORS for `credentials:'include'`

```typescript
// workers/api/posts.ts
const ALLOWED_ORIGINS = new Set([
  'https://my-app.pages.dev',
  'https://my-app.com',
]);

function corsHeaders(origin: string | null): HeadersInit {
  if (!origin || !ALLOWED_ORIGINS.has(origin)) return {};
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Credentials': 'true',
    'Access-Control-Allow-Headers': 'content-type, accept',
    'Access-Control-Max-Age': '86400',
    'Vary': 'Origin',
  };
}

export default {
  async fetch(request: Request, env: { DB: D1Database }): Promise<Response> {
    const origin = request.headers.get('origin');
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }
    const url = new URL(request.url);
    const match = url.pathname.match(/^\/posts\/(\d+)$/);
    if (!match) return new Response('Not found', { status: 404 });
    const post = await env.DB
      .prepare('SELECT title, body FROM posts WHERE id = ?')
      .bind(match[1])
      .first<{ title: string; body: string }>();
    if (!post) return new Response('Not found', { status: 404 });
    return Response.json(post, { headers: corsHeaders(origin) });
  },
} satisfies ExportedHandler<{ DB: D1Database }>;
```

## Turnstile Widget Inside Shadow DOM — Workaround

Turnstile's script renders its iframe by appending to `document.body`, so it cannot be placed inside a shadow root directly. The workaround is to render Turnstile in the light DOM and pass the resulting token into the shadow component via a custom event or attribute:

```typescript
// Light DOM bootstrap (outside any shadow root)
window.turnstileCallback = (token: string) => {
  document.querySelectorAll('auth-form').forEach((el) =>
    el.dispatchEvent(new CustomEvent('turnstile-token', { detail: token }))
  );
};
// The <div id="cf-turnstile"> lives in regular DOM, not inside a shadow root
```

Inside `AuthForm` (a custom element), listen for `'turnstile-token'` on `this` and store it for form submission.

## Declarative Shadow DOM for SSR on Pages

```html
<!-- Served by a Pages Function as pre-rendered HTML -->
<post-card post-id="42" api-base="https://api.example.com">
  <template shadowrootmode="open">
    <style>/* same CSS as above */</style>
    <div class="title">My Pre-rendered Title</div>
    <div class="body">Pre-rendered excerpt …</div>
    <div class="error" hidden></div>
  </template>
</post-card>
```

The browser attaches the shadow DOM from the HTML stream before JavaScript loads, eliminating layout shift. Once the custom element upgrades, `connectedCallback` fires and re-fetches to keep data fresh.

## Anti-patterns

- **`mode:'closed'` for widgets that need third-party script interaction** — closed shadow roots cannot be accessed by external scripts; use `mode:'open'` and rely on CSS encapsulation for isolation.
- **Forgetting `Vary: Origin` on CORS responses** — CDN edges (including Cloudflare's) will serve a cached response with incorrect CORS headers to a different origin without this header.
- **Placing the Turnstile `<script>` tag inside a template clone** — script tags inside `<template>` are inert and will never execute; always add Turnstile in the light DOM document head.
- **Not aborting fetch in `disconnectedCallback`** — a removed element that still awaits a fetch can call `render()` on a detached shadow root, causing silent errors.

## Gotchas

- `attachShadow` can only be called once per element; calling it again throws; guard with `this.shadowRoot` check if the constructor may run multiple times (it should not, but test harnesses sometimes reinstantiate).
- Declarative shadow DOM requires `shadowrootmode` attribute (note: not `shadowroot` — that was the earlier proposal); Safari 16.4+ and Chrome 111+ support it.
- `credentials:'include'` requires the server to return a specific origin in `Access-Control-Allow-Origin` (wildcards are forbidden when credentials are included).
- Custom CSS properties (`--border-color`) pierce shadow DOM boundaries, making them the correct mechanism for host-driven theming.

## Verification

```bash
# Run a local Workers dev server
npx wrangler dev workers/api/posts.ts --d1=DB

# Test CORS preflight
curl -X OPTIONS https://api.example.com/posts/1 \
  -H 'Origin: https://my-app.pages.dev' \
  -H 'Access-Control-Request-Method: GET' -v 2>&1 | grep -i access-control

# Confirm declarative shadow DOM is parsed
# Chrome DevTools > Elements panel > expand <post-card> — look for #shadow-root (open)

# Deploy
npx wrangler pages deploy ./dist --project-name=my-app
```

## Related

- `react-server-components-cloudflare-workers.md`
- `signals-reactivity-angular-cloudflare-pages.md`

## Sources

- MDN Web Components — https://developer.mozilla.org/en-US/docs/Web/API/Web_components
- Declarative Shadow DOM — https://developer.chrome.com/docs/css-ui/declarative-shadow-dom
- Cloudflare Turnstile — https://developers.cloudflare.com/turnstile/
- Cloudflare Workers CORS — https://developers.cloudflare.com/workers/examples/cors-header-proxy/
