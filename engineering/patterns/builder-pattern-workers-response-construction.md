# Builder Pattern: Workers Response Construction

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project API routes produce `Response` objects with overlapping but subtly different requirements — CORS headers on public endpoints, `Cache-Control` for feed responses, `Set-Cookie` on auth flows, structured problem details on errors, and pagination envelopes on list endpoints. Constructing responses with raw `new Response(...)` calls scattered across handlers leads to missing headers, inconsistent error shapes, and copy-paste drift across routes.

## Context

Cloudflare Workers have a native `Response` API that is powerful but imperative. A builder abstracts the assembly of headers, status codes, body serialisation, and envelope wrapping behind a fluent API, producing correct responses by construction. Because Workers have no template engine or framework baseline, a lightweight in-process builder costs nothing in cold-start terms.

## Pattern Overview — ResponseBuilder Interface

The builder accumulates settings through chained methods and materialises the `Response` only when `.build()` is called. A factory method `ResponseBuilder.json()` covers the common case; specialised factory methods handle errors and redirects.

```typescript
// response/builder.ts
const DEFAULT_SECURITY_HEADERS: Record<string, string> = {
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options':        'DENY',
  'Referrer-Policy':        'no-referrer',
};

export interface PaginationMeta {
  cursor:   string | null;
  hasMore:  boolean;
  total?:   number;
}

export class ResponseBuilder {
  private _status:  number                    = 200;
  private _headers: Record<string, string>    = { ...DEFAULT_SECURITY_HEADERS };
  private _body:    BodyInit | null           = null;
  private _envelope: boolean                  = false;
  private _meta:    Record<string, unknown>   = {};

  // ── Factory helpers ──────────────────────────────────────────────────────

  static ok(): ResponseBuilder {
    return new ResponseBuilder();
  }

  static json<T>(data: T): ResponseBuilder {
    return new ResponseBuilder()
      .status(200)
      .header('Content-Type', 'application/json')
      .bodyJSON({ ok: true, data });
  }

  static error(status: number, code: string, detail: string): ResponseBuilder {
    return new ResponseBuilder()
      .status(status)
      .header('Content-Type', 'application/problem+json')
      .bodyJSON({
        type:   `https://example.com/errors/${code}`,
        title:  code,
        status,
        detail,
      });
  }

  static redirect(location: string, permanent = false): ResponseBuilder {
    return new ResponseBuilder()
      .status(permanent ? 301 : 302)
      .header('Location', location)
      .body(null);
  }

  // ── Builder methods ──────────────────────────────────────────────────────

  status(code: number): this {
    this._status = code;
    return this;
  }

  header(name: string, value: string): this {
    this._headers[name] = value;
    return this;
  }

  cors(origin = '*'): this {
    this._headers['Access-Control-Allow-Origin']  = origin;
    this._headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS';
    this._headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization';
    return this;
  }

  cache(maxAge: number, scope: 'public' | 'private' = 'public'): this {
    this._headers['Cache-Control'] = `${scope}, max-age=${maxAge}, s-maxage=${maxAge}`;
    return this;
  }

  noCache(): this {
    this._headers['Cache-Control'] = 'no-store';
    return this;
  }

  cookie(name: string, value: string, opts: { maxAge?: number; httpOnly?: boolean; sameSite?: string } = {}): this {
    const parts = [`${name}=${value}`, 'Path=/'];
    if (opts.maxAge)   parts.push(`Max-Age=${opts.maxAge}`);
    if (opts.httpOnly) parts.push('HttpOnly');
    parts.push(`SameSite=${opts.sameSite ?? 'Lax'}`);
    parts.push('Secure');
    // Append: headers may already have a Set-Cookie entry; append a new directive
    const existing = this._headers['Set-Cookie'];
    this._headers['Set-Cookie'] = existing ? `${existing}, ${parts.join('; ')}` : parts.join('; ');
    return this;
  }

  pagination(meta: PaginationMeta): this {
    this._meta = { ...this._meta, pagination: meta };
    return this;
  }

  requestId(id: string): this {
    this._headers['X-Request-Id'] = id;
    return this;
  }

  body(b: BodyInit | null): this {
    this._body = b;
    return this;
  }

  bodyJSON(obj: unknown): this {
    this._body = JSON.stringify(
      Object.keys(this._meta).length > 0 ? { ...obj as object, meta: this._meta } : obj,
    );
    return this;
  }

  build(): Response {
    return new Response(this._body, {
      status:  this._status,
      headers: this._headers,
    });
  }
}
```

## Implementation — List and Error Helpers

The builder composes cleanly with pagination metadata and RFC 9457 problem details without special-casing in each route.

```typescript
// response/helpers.ts
import { ResponseBuilder, PaginationMeta } from './builder';

export function listResponse<T>(
  items:   T[],
  meta:    PaginationMeta,
  reqId:   string,
  maxAge = 30,
): Response {
  return ResponseBuilder.json({ items })
    .pagination(meta)
    .cache(maxAge, 'public')
    .requestId(reqId)
    .cors()
    .build();
}

export function notFound(detail: string, reqId: string): Response {
  return ResponseBuilder.error(404, 'not_found', detail)
    .requestId(reqId)
    .noCache()
    .build();
}

export function validationError(field: string, detail: string, reqId: string): Response {
  return ResponseBuilder.error(422, 'validation_error', detail)
    .header('X-Invalid-Field', field)
    .requestId(reqId)
    .noCache()
    .build();
}

export function rateLimited(retryAfter: number, reqId: string): Response {
  return ResponseBuilder.error(429, 'rate_limited', 'Too many requests')
    .header('Retry-After', String(retryAfter))
    .requestId(reqId)
    .noCache()
    .build();
}
```

## Workers Integration — Route Handler Usage

Route handlers import helpers and the builder; they never call `new Response(...)` directly. All security and CORS headers are applied consistently without per-route boilerplate.

```typescript
// workers/posts.ts
import { listResponse, notFound, validationError } from '../response/helpers';
import { ResponseBuilder } from '../response/builder';

interface Env { DB: D1Database; }

export async function handleGetFeed(request: Request, env: Env): Promise<Response> {
  const reqId  = request.headers.get('cf-ray') ?? crypto.randomUUID();
  const url    = new URL(request.url);
  const cursor = url.searchParams.get('cursor') ?? undefined;
  const limit  = Math.min(parseInt(url.searchParams.get('limit') ?? '20', 10), 100);

  const { results } = await env.DB
    .prepare(`
      SELECT id, board_slug, body, author_hash, created_at
      FROM posts
      WHERE moderation_status = 'approved'
        AND (? IS NULL OR id < ?)
      ORDER BY id DESC
      LIMIT ?
    `)
    .bind(cursor ?? null, cursor ?? null, limit + 1)
    .all<{ id: string; board_slug: string; body: string; author_hash: string; created_at: number }>();

  const hasMore  = results.length > limit;
  const items    = hasMore ? results.slice(0, limit) : results;
  const nextCursor = hasMore ? items.at(-1)?.id ?? null : null;

  return listResponse(items, { cursor: nextCursor, hasMore }, reqId, 60);
}

export async function handleGetPost(
  request: Request,
  env: Env,
  postId: string,
): Promise<Response> {
  const reqId = request.headers.get('cf-ray') ?? crypto.randomUUID();

  const post = await env.DB
    .prepare('SELECT * FROM posts WHERE id = ? AND moderation_status = ?')
    .bind(postId, 'approved')
    .first<{ id: string; body: string }>();

  if (!post) return notFound(`Post ${postId} not found`, reqId);

  return ResponseBuilder.json(post)
    .cache(120, 'public')
    .cors()
    .requestId(reqId)
    .build();
}
```

## Anti-patterns

- Calling `response.headers.set(...)` after `.build()` — `Response` headers are immutable once constructed; chain before `.build()`
- Concatenating headers as strings inside route handlers — use builder methods to avoid format errors in `Cache-Control` and `Set-Cookie` values
- Returning `new Response(JSON.stringify(data), { status: 200 })` directly in handlers — skips security headers and CORS, causing browser errors on cross-origin requests
- Making `ResponseBuilder` a singleton — it carries mutable state; instantiate per-request via factory methods

## Gotchas

- `Set-Cookie` with multiple values: the `Response` constructor does not support multiple `Set-Cookie` header values via a plain object; use `new Headers()` and `headers.append('Set-Cookie', ...)` for multiple cookies, or serialise them comma-separated (which some proxies misparse). Prefer one cookie per response where possible.
- Cloudflare strips certain response headers (e.g., `Server`) at the edge regardless of what the Worker sets; do not rely on them being present in production
- `Cache-Control: s-maxage` affects Cloudflare's edge cache; `max-age` affects the browser. Setting both correctly enables layered caching
- `cf-ray` is available in production but not in `wrangler dev` local mode; the fallback to `crypto.randomUUID()` handles this

## Verification

```typescript
// vitest unit test — no Workers runtime needed
import { ResponseBuilder } from './response/builder';
import { listResponse, notFound } from './response/helpers';

test('json response has security headers', async () => {
  const res = ResponseBuilder.json({ id: '1' }).build();
  expect(res.headers.get('X-Content-Type-Options')).toBe('nosniff');
  expect(res.headers.get('Content-Type')).toBe('application/json');
  expect(res.status).toBe(200);
});

test('listResponse includes pagination meta', async () => {
  const res = listResponse([{ id: '1' }], { cursor: 'abc', hasMore: true }, 'req-1');
  const body = await res.json() as any;
  expect(body.meta.pagination.hasMore).toBe(true);
  expect(body.meta.pagination.cursor).toBe('abc');
});

test('notFound returns 404 with problem+json', async () => {
  const res = notFound('Post not found', 'req-2');
  expect(res.status).toBe(404);
  expect(res.headers.get('Content-Type')).toBe('application/problem+json');
});
```

## Related

- `error-codes-and-responses.md` — standardised error code registry for the platform
- `http-api-problem-details-safe-error-contracts.md` — RFC 9457 problem details format
- `api-rate-limiting-detail.md` — rate limit header conventions (`Retry-After`, `X-RateLimit-*`)
- `correlation-id-propagation-workers.md` — request ID propagation across Worker chains
- `decorator-pattern-workers-middleware-composition.md` — wrapping handlers to inject headers at a higher level

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/response/
- https://developers.cloudflare.com/cache/concepts/cache-control/
- https://www.rfc-editor.org/rfc/rfc9457 (Problem Details for HTTP APIs)
- https://refactoring.guru/design-patterns/builder
