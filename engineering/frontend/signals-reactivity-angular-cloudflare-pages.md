# Angular 17+ Signals-Based Reactivity on Cloudflare Pages

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You are migrating an Angular application to signals-based reactivity (Angular 17+) and deploying it on Cloudflare Pages with server-side rendering via `@angular/ssr`. Hydration mismatches occur when the Pages Function adapter renders the app with different data than the client hydrates with, and the Content Security Policy nonces required by Angular's SSR do not survive the CDN caching layer.

## Context

Angular 17 introduced first-class signal primitives — `signal()`, `computed()`, and `effect()` — that enable fine-grained reactivity without Zone.js change detection overhead. `@angular/ssr` wraps `@angular/platform-server` and provides an Express-compatible handler that can be adapted to run in a Cloudflare Pages Function. Static routes can be prerendered at build time with `ng build --prerender`, while dynamic routes are server-rendered on demand. CSP nonces prevent XSS in Angular's inline styles and scripts; Cloudflare Pages injects them via the `_headers` file and a custom `TransferState` key.

## Signal Primitives in a Component

```typescript
// src/app/features/posts/posts.component.ts
import {
  Component, inject, signal, computed, effect, OnInit
} from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

interface Post {
  id: number;
  title: string;
  category: string;
}

@Component({
  selector: 'app-posts',
  standalone: true,
  template: `
    <input
      placeholder="Filter posts…"
      (input)="filter.set($any($event.target).value)"
    />
    <p>Showing {{ visibleCount() }} of {{ posts().length }} posts</p>
    @if (loading()) {
      <div class="skeleton-list"></div>
    } @else {
      <ul>
        @for (post of filteredPosts(); track post.id) {
          <li>{{ post.title }}</li>
        }
      </ul>
    }
    @if (error()) {
      <p class="error">{{ error() }}</p>
    }
  `,
})
export class PostsComponent implements OnInit {
  private http = inject(HttpClient);

  posts    = signal<Post[]>([]);
  filter   = signal('');
  loading  = signal(true);
  error    = signal<string | null>(null);

  filteredPosts = computed(() => {
    const q = this.filter().toLowerCase();
    return q
      ? this.posts().filter((p) => p.title.toLowerCase().includes(q))
      : this.posts();
  });

  visibleCount = computed(() => this.filteredPosts().length);

  constructor() {
    // Log whenever the visible count changes — useful for analytics
    effect(() => {
      console.debug(`[posts] visible: ${this.visibleCount()}`);
    });
  }

  async ngOnInit(): Promise<void> {
    try {
      const posts = await firstValueFrom(
        this.http.get<Post[]>('/api/posts')
      );
      this.posts.set(posts);
    } catch (err) {
      this.error.set((err as Error).message);
    } finally {
      this.loading.set(false);
    }
  }
}
```

## SSR with `@angular/ssr` and Pages Functions Adapter

```typescript
// functions/ssr.ts  (Cloudflare Pages Function)
import { CommonEngine } from '@angular/ssr';
import bootstrap from '../src/main.server';

interface Env {
  ASSETS: Fetcher;
}

const engine = new CommonEngine();

export const onRequest: PagesFunction<Env> = async (ctx) => {
  const { request } = ctx;
  const url = new URL(request.url);

  // Let the edge serve static assets directly
  if (/\.[a-z]{2,4}$/i.test(url.pathname)) {
    return ctx.env.ASSETS.fetch(request);
  }

  // Generate a per-request CSP nonce
  const nonce = crypto.randomUUID().replace(/-/g, '');

  const html = await engine.render({
    url: url.href,
    bootstrap,
    // Inject nonce so Angular uses it for inline styles
    publicPath: '/',
    inlineCriticalCss: false,
    providers: [
      {
        provide: 'CSP_NONCE',
        useValue: nonce,
      },
    ],
  });

  return new Response(html, {
    headers: {
      'content-type': 'text/html; charset=utf-8',
      // CSP header references the nonce; short TTL prevents nonce reuse
      'content-security-policy':
        `script-src 'nonce-${nonce}' 'strict-dynamic'; ` +
        `style-src 'nonce-${nonce}' 'unsafe-inline';`,
      'cache-control': 'public, max-age=0, must-revalidate',
    },
  });
};
```

## `HttpClient` Fetching from Workers API

```typescript
// src/app/core/api.interceptor.ts
import { HttpInterceptorFn } from '@angular/common/http';
import { isPlatformServer } from '@angular/common';
import { inject, PLATFORM_ID } from '@angular/core';

export const apiBaseInterceptor: HttpInterceptorFn = (req, next) => {
  const isServer = isPlatformServer(inject(PLATFORM_ID));
  // On the server, prefix relative URLs with the Workers API origin
  if (isServer && req.url.startsWith('/api')) {
    const serverReq = req.clone({
      url: `https://api.example.com${req.url}`,
    });
    return next(serverReq);
  }
  return next(req);
};
```

Register in `app.config.ts`:

```typescript
import { provideHttpClient, withInterceptors, withFetch } from '@angular/common/http';

export const appConfig = {
  providers: [
    provideHttpClient(
      withFetch(),                          // Use the Fetch API (required in Workers)
      withInterceptors([apiBaseInterceptor])
    ),
  ],
};
```

## Prerendering Static Routes

```json
// angular.json (build target excerpt)
{
  "prerender": {
    "routesFile": "prerender-routes.txt"
  }
}
```

```
# prerender-routes.txt
/
/about
/pricing
/blog
```

```bash
ng build --configuration production
# Outputs prerendered HTML into dist/browser/ for static Pages serving
```

Dynamic routes (e.g. `/blog/:slug`) fall through to the SSR Pages Function at runtime.

## `_headers` for CSP Nonce Integration

```
# public/_headers

# Prerendered static pages get a static CSP; nonce is not needed (no inline scripts)
/
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'
  Cache-Control: public, max-age=0, must-revalidate

/about
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'
  Cache-Control: public, max-age=0, must-revalidate

# Hashed JS/CSS assets — long TTL
/assets/*
  Cache-Control: public, max-age=31536000, immutable
```

SSR responses (served by the Pages Function) set their own `Content-Security-Policy` header with the per-request nonce (as shown in the adapter above); `_headers` rules apply only to static asset responses.

## Anti-patterns

- **Using `effect()` to synchronise two signals** — `effect()` is for side-effects (logging, DOM manipulation); use `computed()` to derive values from other signals; circular effect updates cause infinite loops.
- **Zone.js with signals** — if you have removed Zone.js (`"zone.js"` removed from `polyfills` in `angular.json`), `ChangeDetectorRef.markForCheck()` calls become no-ops; ensure all component inputs are signals or use `ChangeDetectionStrategy.OnPush`.
- **Caching SSR responses with CSP nonces** — a cached response with a stale nonce will block all inline scripts for subsequent visitors; always set `Cache-Control: no-store` or `max-age=0, must-revalidate` on SSR responses.
- **`withInterceptors` without `withFetch()`** — Angular SSR in Workers requires the Fetch-based HTTP backend; the default `XMLHttpRequest` backend throws in the Workers runtime.

## Gotchas

- `CommonEngine` is not tree-shaken; it imports the full `@angular/platform-server` which adds ~200 kB to your Pages Function bundle — set `minify: true` in Wrangler and check the bundle size with `wrangler deploy --dry-run --outdir dist-worker`.
- `signal()` values are compared with `Object.is`; mutating an object inside a signal (e.g. `mySignal().items.push(x)`) does **not** trigger reactivity — always replace with a new reference (`mySignal.update(s => ({ ...s, items: [...s.items, x] }))`).
- Prerendered pages are served as static files by Pages ASSETS; they bypass the SSR Pages Function — ensure your `_routes.json` excludes prerendered paths from Function invocation to avoid double-rendering costs.
- The `CSP_NONCE` injection token (`InjectionToken<string>`) is available in `@angular/core` from v16; do not create a custom token with the same name as it may conflict with Angular internals.

## Verification

```bash
# Build with prerender
ng build --configuration production

# Inspect prerendered output
ls dist/browser/
cat dist/browser/index.html | grep '<script'

# Run the Pages Function locally
npx wrangler pages dev dist/browser --compatibility-date=2025-09-01

# Verify CSP nonce in SSR response
curl -s http://localhost:8788/blog/my-post | grep 'nonce-'

# Deploy
npx wrangler pages deploy dist/browser --project-name=my-ng-app
```

## Related

- `vite-cloudflare-pages-build-optimization.md`
- `web-components-shadow-dom-workers-api.md`

## Sources

- Angular Signals guide — https://angular.dev/guide/signals
- Angular SSR — https://angular.dev/guide/ssr
- Cloudflare Pages Functions — https://developers.cloudflare.com/pages/functions/
- Angular CSP nonce — https://angular.dev/best-practices/security#content-security-policy
