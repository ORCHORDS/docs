# HTTP Parameter Pollution (HPP) Prevention in Cloudflare Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A Cloudflare Worker receives query strings or form bodies from clients. An attacker submits a request with duplicate parameter names:

```
GET /api/search?category=electronics&category=admin HTTP/1.1
POST /api/order  body: item=widget&qty=1&qty=999
```

Depending on how the Worker parses these parameters, the result may be:

- The first value used (safe for that specific key)
- The last value used (the attacker's injected value wins)
- An array of all values (upstream logic expects a string, receives an array, causing type errors or bypassing validation)
- A comma-joined string (`electronics,admin`) that bypasses allowlist checks

HTTP Parameter Pollution (HPP) exploits the inconsistency between how a client library produces parameters and how the server consumes them. In Workers it manifests in query string parsing, `URLSearchParams`, form body parsing, JSON arrays, and proxy forwarding.

## Context

The HTTP spec does not define behavior for duplicate query parameters. Different parsers handle them differently:

| Parser / Platform | Behavior for `?a=1&a=2` |
|-------------------|-------------------------|
| `URLSearchParams.get('a')` | `"1"` (first value) |
| `URLSearchParams.getAll('a')` | `["1", "2"]` |
| PHP | `"2"` (last value) |
| Express.js (qs) | `["1", "2"]` or `{a: "2"}` depending on config |
| Cloudflare Workers (URLSearchParams) | First value via `.get()`, all values via `.getAll()` |

The risk in Workers specifically:

1. **Proxy forwarding**: A Worker receives a request, validates one layer of parameters, then forwards the raw URL to a backend. The backend may parse the same URL differently and see a different value.
2. **Type confusion**: A function expects a string from `url.searchParams.get('id')` but a bug in an array-path returns an array. Downstream code using `.toLowerCase()` throws a TypeError at runtime.
3. **WAF bypass**: Cloudflare WAF rules inspect query parameters. A rule that blocks `role=admin` might not trigger on the second occurrence of a duplicate `role` parameter.

## Parsing Query Parameters Safely

Never read raw query strings. Always extract exactly one value per parameter and validate its type:

```typescript
// src/lib/params.ts

/**
 * Safely extract a single string query parameter.
 * Returns null if the parameter is absent.
 * Throws if the parameter appears more than once (HPP attempt).
 */
export function getSingleParam(
  url: URL,
  name: string,
  opts: { maxLength?: number } = {},
): string | null {
  const values = url.searchParams.getAll(name);

  if (values.length === 0) return null;

  if (values.length > 1) {
    throw new ParamError(`Duplicate parameter "${name}" is not permitted`);
  }

  const value = values[0];

  if (opts.maxLength && value.length > opts.maxLength) {
    throw new ParamError(`Parameter "${name}" exceeds maximum length of ${opts.maxLength}`);
  }

  return value;
}

/**
 * Safely extract an integer query parameter.
 */
export function getIntParam(
  url: URL,
  name: string,
  opts: { min?: number; max?: number } = {},
): number | null {
  const raw = getSingleParam(url, name);
  if (raw === null) return null;

  const n = Number(raw);
  if (!Number.isInteger(n)) throw new ParamError(`Parameter "${name}" must be an integer`);
  if (opts.min !== undefined && n < opts.min) throw new ParamError(`Parameter "${name}" below minimum`);
  if (opts.max !== undefined && n > opts.max) throw new ParamError(`Parameter "${name}" above maximum`);

  return n;
}

/**
 * Safely extract an enum query parameter — only allow values in the provided set.
 */
export function getEnumParam<T extends string>(
  url: URL,
  name: string,
  allowed: readonly T[],
): T | null {
  const raw = getSingleParam(url, name);
  if (raw === null) return null;
  if (!allowed.includes(raw as T)) {
    throw new ParamError(`Parameter "${name}" value "${raw}" is not permitted`);
  }
  return raw as T;
}

export class ParamError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ParamError';
  }
}
```

Usage in a handler:

```typescript
// src/handlers/search.ts
import { getSingleParam, getIntParam, getEnumParam, ParamError } from '../lib/params';

const ALLOWED_CATEGORIES = ['electronics', 'clothing', 'books', 'home'] as const;

export async function handleSearch(req: Request, env: Env): Promise<Response> {
  const url = new URL(req.url);

  let query: string | null;
  let page: number | null;
  let category: typeof ALLOWED_CATEGORIES[number] | null;

  try {
    query    = getSingleParam(url, 'q', { maxLength: 200 });
    page     = getIntParam(url, 'page', { min: 1, max: 1000 });
    category = getEnumParam(url, 'category', ALLOWED_CATEGORIES);
  } catch (err) {
    if (err instanceof ParamError) {
      return new Response(JSON.stringify({ error: err.message }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    throw err;
  }

  // Proceed with validated, single-value parameters
  const results = await searchProducts(env.DB, { query, page: page ?? 1, category });
  return new Response(JSON.stringify({ results }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}
```

## Form Body Parsing (application/x-www-form-urlencoded)

Form bodies have the same duplication risk as query strings. Parse them through the same safe wrapper:

```typescript
// src/lib/form-params.ts
import { ParamError } from './params';

/**
 * Parse a form body and enforce no-duplicate-parameter policy.
 */
export async function parseFormBody(req: Request): Promise<Map<string, string>> {
  const text = await req.text();
  const params = new URLSearchParams(text);
  const result = new Map<string, string>();

  for (const key of new Set(params.keys())) {
    const values = params.getAll(key);
    if (values.length > 1) {
      throw new ParamError(`Duplicate form parameter "${key}" is not permitted`);
    }
    result.set(key, values[0]);
  }

  return result;
}
```

## JSON Body Duplicate Key Handling

JSON does not formally prohibit duplicate keys, but most parsers silently use the last value. A malicious body like `{"role":"user","role":"admin"}` causes the last `role` to win after parsing:

```typescript
// src/lib/json-parse.ts

/**
 * Parse a JSON body and detect duplicate keys.
 * Workers' native JSON.parse does not detect duplicates;
 * use a reviver-based approach or a JSON5 parser in strict mode.
 *
 * Simple approach: compare raw key count vs parsed object key count.
 */
export async function parseStrictJson<T extends object>(req: Request): Promise<T> {
  const text = await req.text();

  // Count raw key occurrences using a quick regex scan
  // This is heuristic — use a proper streaming JSON parser for production
  const keyMatches = text.match(/"([^"\\]|\\.)*"\s*:/g) ?? [];
  const rawKeys = keyMatches.map(m => m.replace(/\s*:$/, '').replace(/^"|"$/g, ''));
  const uniqueKeys = new Set(rawKeys);

  if (rawKeys.length !== uniqueKeys.size) {
    const duplicates = rawKeys.filter((k, i) => rawKeys.indexOf(k) !== i);
    throw new Error(`JSON body contains duplicate keys: ${[...new Set(duplicates)].join(', ')}`);
  }

  return JSON.parse(text) as T;
}
```

For production use, `@hapi/hoek`'s JSON scanner or a custom streaming parser gives more reliable duplicate detection. At minimum, define which fields from the body you trust and whitelist-extract them:

```typescript
// Safer pattern: destructure only what you need from the parsed body
const body = await req.json<Record<string, unknown>>();
const role   = typeof body.role   === 'string' ? body.role   : null;
const action = typeof body.action === 'string' ? body.action : null;
// Never spread body.* into a trusted operation
```

## Safe URL Forwarding to Backend APIs

When a Worker acts as a proxy, reconstruct the URL rather than forwarding the raw query string:

```typescript
// src/lib/proxy.ts

/**
 * Forward a request to a backend API, reconstructing the query string
 * from validated parameters to prevent HPP from reaching the backend.
 */
export function buildBackendUrl(
  backendBase: string,
  path: string,
  validatedParams: Record<string, string | number | null>,
): string {
  const url = new URL(path, backendBase);

  for (const [key, value] of Object.entries(validatedParams)) {
    if (value !== null && value !== undefined) {
      // setSearchParam replaces any existing value — no duplication possible
      url.searchParams.set(key, String(value));
    }
  }

  return url.toString();
}

// Example usage
const backendUrl = buildBackendUrl(
  'https://internal-api.example.com',
  '/search',
  { q: query, page: page ?? 1, category: category ?? undefined },
);

const backendResp = await fetch(backendUrl, {
  headers: { 'X-Internal-Secret': env.INTERNAL_API_SECRET },
});
```

## HPP in Path Segments

Path segments can also carry duplicate-like confusion via matrix parameters or semicolons:

```
/api/users;admin=true/profile
/api/path/to/../456
```

Normalize path segments before routing:

```typescript
// src/lib/path.ts

export function normalizePath(rawPath: string): string {
  // Resolve dot segments
  const url = new URL(rawPath, 'https://internal');
  return url.pathname;  // URL constructor resolves ../ and ./
}

export function extractPathSegment(path: string, index: number): string {
  // Strip matrix parameters (semicolons) from each segment
  return path.split('/').filter(Boolean)[index]?.split(';')[0] ?? '';
}
```

## Anti-patterns

- **Using `url.searchParams.get()` without checking for duplicates**: `.get()` silently returns the first occurrence. An attacker can append `&admin=true` after a legitimate parameter and have it ignored by `.get()`, but picked up by a backend that uses last-wins semantics.
- **Forwarding the raw `req.url` to a backend without reconstruction**: The raw URL may contain duplicated parameters that the backend parses differently. Always reconstruct with `url.searchParams.set()`.
- **Trusting JSON bodies without type-checking each field**: `typeof body.role === 'string'` is not redundant; the attacker controls the JSON and can send `{"role": ["user", "admin"]}`, which makes `role` an array, not a string.
- **Logging raw query strings in structured logs**: Duplicate parameters in logs can confuse log parsers and potentially inject log entries. Sanitize or strip duplicate keys before logging.
- **Allowing arbitrary arrays in query params**: Libraries that turn `?ids[]=1&ids[]=2` into an array are convenient but increase the HPP attack surface. Explicitly document and validate every parameter that accepts multiple values.

## Gotchas

- **`URLSearchParams` iteration order**: When iterating `url.searchParams.entries()`, duplicate keys appear as separate entries in insertion order. Code that stops at the first match is safe; code that iterates all entries may process duplicates.
- **Worker subrequest URL limits**: Cloudflare Workers enforce a limit on URL length. An attacker flooding duplicate parameters can cause a 414 URI Too Long response, potentially masking a legitimate request. Rate-limit by IP before URL parsing.
- **Encoding tricks**: `%26` in a query value is a literal `&` after decoding, not a parameter separator. URLSearchParams handles this correctly, but raw string splitting on `&` does not. Always use URLSearchParams, never split on `&` manually.
- **Headers with duplicate names**: HTTP headers can also be duplicated (`X-User-Id: alice\r\nX-User-Id: admin`). `req.headers.get('X-User-Id')` in Workers returns the first value; `req.headers.getAll('X-User-Id')` returns all. Apply the same single-value enforcement to trusted headers.

## Verification

```bash
# 1. Send a duplicate parameter — expect 400 with "Duplicate parameter" error
curl -s "https://api.example.com/api/search?q=widget&category=electronics&category=admin" \
  | jq .error

# 2. Test category allowlist enforcement
curl -s "https://api.example.com/api/search?category=../../../../etc/passwd" \
  | jq .error

# 3. Test form body duplication
curl -s -X POST "https://api.example.com/api/order" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "item=widget&qty=1&qty=999" \
  | jq .error

# 4. Automated fuzz test with all parameters duplicated (use a tool like ffuf or Burp Intruder)
# ffuf -u "https://api.example.com/api/search?FUZZ" \
#   -w /path/to/dup-params-wordlist.txt -mc 200
```

## Related

- `sql-injection-prevention-d1-workers.md`
- `mass-assignment-prevention.md`
- `server-side-request-forgery-ssrf.md`
- `idor-insecure-direct-object-reference.md`
- `owasp-api-top-10-2023.md`

## Sources

- OWASP HPP Testing Guide: https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/07-Input_Validation_Testing/04-Testing_for_HTTP_Parameter_Pollution
- RFC 3986 (URI syntax): https://datatracker.ietf.org/doc/html/rfc3986
- URLSearchParams specification: https://url.spec.whatwg.org/#interface-urlsearchparams
- Cloudflare Workers Request API: https://developers.cloudflare.com/workers/runtime-apis/request/
