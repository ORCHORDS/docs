# Capacitor HTTP Plugin CORS Configuration with Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Capacitor apps using `@capacitor/http` (or the legacy `@ionic-native/http`) bypass the
WebView's CORS enforcement on iOS and Android, but Workers must still respond correctly to
preflight `OPTIONS` requests for web-based builds and for same-origin policy enforcement on
newer Capacitor versions. Teams that configure CORS only for simple requests start seeing
`Network Error` on PUT, PATCH, DELETE, or any request with a custom `Authorization` header
when running in the browser during development.

## Context

Capacitor's HTTP plugin sends requests natively on device, which sidesteps CORS entirely for
those builds. However, the same codebase may run as a PWA in the browser, and Capacitor's
`web` fallback re-uses `fetch`, which is subject to CORS. Additionally, Ionic's `Capacitor.getPlatform()`
returns `'web'` in the browser-based dev server, meaning your Workers must respond correctly
to `OPTIONS` preflights for the full developer experience to work. A single Workers CORS
middleware covers both cases without platform-branching in the mobile codebase.

## Workers CORS Middleware

```typescript
// workers/src/middleware/cors.ts

export interface CorsOptions {
  /** Allowed origin patterns. Pass ['*'] for public APIs. */
  allowedOrigins: string[];
  allowedMethods?: string[];
  allowedHeaders?: string[];
  maxAge?: number;
  credentials?: boolean;
}

const DEFAULT_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'];
const DEFAULT_HEADERS = [
  'Authorization',
  'Content-Type',
  'X-Requested-With',
  'X-Capacitor-Platform',
  'X-App-Version',
];

function matchOrigin(origin: string, patterns: string[]): boolean {
  return patterns.some(p => {
    if (p === '*') return true;
    if (p === origin) return true;
    // Support wildcarded subdomains: *.example.com
    if (p.startsWith('*.')) {
      const suffix = p.slice(1); // .example.com
      return origin.endsWith(suffix);
    }
    return false;
  });
}

export function withCors(
  handler: (req: Request) => Promise<Response>,
  opts: CorsOptions
): (req: Request) => Promise<Response> {
  const methods = opts.allowedMethods ?? DEFAULT_METHODS;
  const headers = opts.allowedHeaders ?? DEFAULT_HEADERS;
  const maxAge = opts.maxAge ?? 86400;

  return async (req: Request): Promise<Response> => {
    const origin = req.headers.get('Origin') ?? '';
    const allowed = matchOrigin(origin, opts.allowedOrigins);

    // Preflight
    if (req.method === 'OPTIONS') {
      const res = new Response(null, { status: 204 });
      if (allowed) {
        res.headers.set('Access-Control-Allow-Origin', origin || '*');
        res.headers.set('Access-Control-Allow-Methods', methods.join(', '));
        res.headers.set('Access-Control-Allow-Headers', headers.join(', '));
        res.headers.set('Access-Control-Max-Age', String(maxAge));
        if (opts.credentials) {
          res.headers.set('Access-Control-Allow-Credentials', 'true');
        }
      }
      return res;
    }

    // Actual request
    const res = await handler(req);
    const mutable = new Response(res.body, res);

    if (allowed) {
      mutable.headers.set('Access-Control-Allow-Origin', origin || '*');
      if (opts.credentials) {
        mutable.headers.set('Access-Control-Allow-Credentials', 'true');
      }
      mutable.headers.append(
        'Vary',
        'Origin, Access-Control-Request-Headers'
      );
    }

    return mutable;
  };
}

// workers/src/index.ts
import { withCors } from './middleware/cors';

const corsConfig = {
  allowedOrigins: [
    'capacitor://localhost',       // iOS native
    'http://localhost',            // Android native (Capacitor uses http)
    '*.example.com',               // Web builds
    'http://localhost:8100',       // Ionic dev server
    'http://localhost:4200',       // Angular CLI
  ],
  credentials: true,
  maxAge: 3600,
};

export default {
  fetch: withCors(async (req) => {
    return Response.json({ ok: true });
  }, corsConfig),
};
```

## Capacitor HTTP Plugin Setup

```typescript
// src/lib/capacitorHttp.ts
import { CapacitorHttp, HttpOptions, HttpResponse } from '@capacitor/http';
import { Capacitor } from '@capacitor/core';

const WORKERS_BASE = import.meta.env.VITE_WORKERS_URL ?? 'https://api.example.com';

export async function workersRequest<T>(
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  options: {
    data?: unknown;
    params?: Record<string, string>;
    token?: string;
  } = {}
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Capacitor-Platform': Capacitor.getPlatform(),
    'X-App-Version': import.meta.env.VITE_APP_VERSION ?? 'dev',
  };

  if (options.token) {
    headers['Authorization'] = `Bearer ${options.token}`;
  }

  const requestOptions: HttpOptions = {
    url: `${WORKERS_BASE}${path}`,
    method,
    headers,
    ...(options.params ? { params: options.params } : {}),
    ...(options.data != null ? { data: options.data } : {}),
    // Capacitor HTTP native: disableRedirects not needed for Workers
    webFetchExtra: {
      // Used only on web platform — ensures credentials are sent for
      // Workers endpoints that set Access-Control-Allow-Credentials
      credentials: 'include',
    },
  };

  let res: HttpResponse;
  try {
    res = await CapacitorHttp.request(requestOptions);
  } catch (err) {
    throw new Error(`Network error calling ${path}: ${String(err)}`);
  }

  if (res.status < 200 || res.status >= 300) {
    const body = typeof res.data === 'object' ? JSON.stringify(res.data) : String(res.data);
    throw new Error(`Workers ${res.status} on ${path}: ${body}`);
  }

  return res.data as T;
}
```

## Preflight Caching and Vary Header Strategy

```typescript
// workers/src/middleware/cors-cache.ts
// Cloudflare caches preflight responses — ensure Vary is set correctly
// to prevent cross-origin cache poisoning.

export function preflightCacheHeaders(res: Response): Response {
  const mutable = new Response(res.body, res);

  // Workers cache respects Vary: this prevents a cached OPTIONS response
  // from one origin being served to a different origin
  mutable.headers.set('Vary', 'Origin, Access-Control-Request-Method, Access-Control-Request-Headers');

  // Cache preflight at Cloudflare edge for 1 hour
  mutable.headers.set('Cache-Control', 'public, max-age=3600');

  return mutable;
}

// capacitor.config.ts — hostname config for native platforms
// This ensures iOS native uses capacitor://localhost as Origin
// and Android uses http://localhost (Capacitor default)
export default {
  appId: 'com.example.app',
  appName: 'ExampleApp',
  webDir: 'dist',
  server: {
    androidScheme: 'http', // must match Workers allowedOrigins
    iosScheme: 'capacitor', // must match Workers allowedOrigins
    hostname: 'localhost',
  },
};
```

## Anti-patterns

- Configuring `Access-Control-Allow-Origin: *` globally for authenticated endpoints — the
  wildcard is rejected by browsers when `credentials: 'include'` is set; you must echo back
  the specific request `Origin`.
- Forgetting `Vary: Origin` on cached responses — Cloudflare's edge cache will serve a
  cached `Access-Control-Allow-Origin: capacitor://localhost` header to browser clients that
  expected their own origin, causing silent CORS failures.
- Using `@ionic-native/http` (Cordova) in new Capacitor 5+ projects — use `@capacitor/http`
  which handles the Android `http://` vs `https://` scheme correctly for Workers.

## Gotchas

- On Android, Capacitor sets the `Origin` header to `http://localhost`, not
  `capacitor://localhost` — both origins must be in your Workers allowlist if you serve iOS
  and Android from the same Worker.
- Workers `new Response(res.body, res)` does not copy `Set-Cookie` headers because `Response`
  strips them during clone — use `res.headers.getAll('Set-Cookie')` and re-append after
  cloning if your Workers endpoint sets cookies.

## Verification

```bash
# Start Workers dev server
npx wrangler dev --port 8787

# Simulate Capacitor iOS preflight
curl -si -X OPTIONS http://localhost:8787/api/products \
  -H "Origin: capacitor://localhost" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Authorization, Content-Type" \
  | grep -i 'access-control'

# Simulate Capacitor Android preflight
curl -si -X OPTIONS http://localhost:8787/api/products \
  -H "Origin: http://localhost" \
  -H "Access-Control-Request-Method: PUT" \
  | grep -i 'access-control'

# Simulate browser (Ionic dev server) preflight
curl -si -X OPTIONS http://localhost:8787/api/products \
  -H "Origin: http://localhost:8100" \
  -H "Access-Control-Request-Method: DELETE" \
  | grep -i 'access-control'
```

## Related

- `mobile/capacitor-native-bridge-plugin-development.md`
- `mobile/capacitor-d1-sqlite-offline-sync.md`
- `mobile/ios-app-transport-security.md`

## Sources

- https://developers.cloudflare.com/workers/examples/cors-header-proxy/
- https://capacitorjs.com/docs/apis/http
- https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS
