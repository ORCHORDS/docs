# Mobile API Versioning Strategy with Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your mobile app ships to millions of devices across app-store update cycles measured in weeks. The API must evolve — new fields, changed response shapes, removed endpoints — without breaking clients that are one or two versions behind. You need a versioning strategy for Cloudflare Workers that supports URL-path versioning, header versioning, a minimum-version gate for security patches, and deprecation signals to clients.

## Context

Mobile API versioning differs from web API versioning: clients cannot be force-updated instantly. A version in production today may remain active for 6–12 months after the next major release. The strategy must handle:

- **URL path versioning** (`/v1/`, `/v2/`) — explicit, cache-friendly, easy to curl.
- **Header versioning** (`Accept-Version: 2`) — cleaner URLs but requires `Vary` header for CDN caching.
- **Min-version enforcement** — a KV flag that raises the floor without redeployment (for emergency security patches).
- **Deprecation signals** — `Sunset` (RFC 8594) and `Deprecation` (RFC 9512) response headers so mobile SDKs can surface upgrade prompts.

## Solution

```typescript
export interface Env {
  DB: D1Database;
  KV: KVNamespace;
}

// Bump these as you ship new API versions
const VERSION_CONFIG = {
  current: 3,
  minimum: 2,           // versions below this receive 410 Gone
  deprecated: [1],      // still served but flagged for removal
  sunset: {
    1: 'Sat, 31 Dec 2026 23:59:59 GMT',
    2: 'Sat, 30 Jun 2027 23:59:59 GMT',
  } as Record<number, string>,
};

type Version = number;

// --- Version extraction (URL path wins over headers) ---

function extractVersion(request: Request): Version | null {
  const url = new URL(request.url);

  const pathMatch = url.pathname.match(/^\/v(\d+)\//);
  if (pathMatch) return parseInt(pathMatch[1], 10);

  const acceptVersion = request.headers.get('Accept-Version');
  if (acceptVersion) {
    const v = parseInt(acceptVersion, 10);
    if (!isNaN(v)) return v;
  }

  // Legacy header kept for backward compat with old SDK versions
  const legacyHeader = request.headers.get('X-API-Version');
  if (legacyHeader) {
    const v = parseInt(legacyHeader, 10);
    if (!isNaN(v)) return v;
  }

  return null;
}

// --- Min-version gate (static config + KV dynamic override) ---

async function getEffectiveMinVersion(env: Env): Promise<number> {
  // KV allows raising the floor for security patches without redeployment.
  // New value takes effect within ~60 s globally (KV consistency window).
  const override = await env.KV.get('api:min_version');
  return override ? parseInt(override, 10) : VERSION_CONFIG.minimum;
}

function versionTooOldResponse(version: number, minimum: number): Response {
  return Response.json(
    {
      error: 'API_VERSION_TOO_OLD',
      message: `API version ${version} is no longer supported. Minimum: ${minimum}.`,
      upgrade_url: 'https://example.com/docs/api/migration',
      minimum_version: minimum,
      current_version: VERSION_CONFIG.current,
    },
    { status: 410 },
  );
}

// --- Deprecation response headers ---

function addVersionHeaders(response: Response, version: Version): Response {
  const headers = new Headers(response.headers);
  headers.set('X-API-Version', String(version));
  headers.set('X-API-Current-Version', String(VERSION_CONFIG.current));

  if (VERSION_CONFIG.deprecated.includes(version)) {
    const sunset = VERSION_CONFIG.sunset[version];
    headers.set('Deprecation', 'true');
    if (sunset) {
      headers.set('Sunset', sunset);
      headers.set(
        'Warning',
        `299 - "API v${version} is deprecated and will be removed ${sunset}"`,
      );
    }
    headers.set(
      'Link',
      `<https://example.com/docs/api/v${version}-migration>; rel="deprecation", ` +
      `<https://example.com/docs/api/v${VERSION_CONFIG.current}>; rel="successor-version"`,
    );
  }

  return new Response(response.body, { status: response.status, headers });
}

// --- Version-aware route handlers ---

type RouteHandler = (request: Request, env: Env, version: Version) => Promise<Response>;

async function handleGetUser(
  request: Request,
  env: Env,
  version: Version,
): Promise<Response> {
  const url = new URL(request.url);
  const userId = url.pathname.split('/').pop()!;

  const user = await env.DB.prepare('SELECT * FROM users WHERE id = ?')
    .bind(userId)
    .first<Record<string, unknown>>();

  if (!user) return new Response('Not found', { status: 404 });

  // v1: flat structure (legacy mobile SDK)
  if (version <= 1) {
    return Response.json({ id: user.id, name: user.name, email: user.email });
  }

  // v2: nested profile object
  if (version === 2) {
    return Response.json({
      id: user.id,
      profile: { name: user.name, email: user.email },
    });
  }

  // v3+: full object with settings and timestamps
  return Response.json({
    id: user.id,
    profile: { name: user.name, email: user.email },
    settings: JSON.parse((user.settings as string) ?? '{}'),
    created_at: user.created_at,
  });
}

async function handleCreateUser(
  request: Request,
  env: Env,
  version: Version,
): Promise<Response> {
  const body = await request.json<Record<string, unknown>>();

  // v1 accepted top-level name/email; v2+ uses a nested profile object
  const name = version <= 1
    ? (body.name as string)
    : (body.profile as Record<string, string>)?.name;
  const email = version <= 1
    ? (body.email as string)
    : (body.profile as Record<string, string>)?.email;

  if (!name || !email) {
    return Response.json(
      { error: 'VALIDATION_ERROR', fields: ['name', 'email'] },
      { status: 422 },
    );
  }

  const id = crypto.randomUUID();
  await env.DB.prepare(
    'INSERT INTO users (id, name, email, created_at) VALUES (?, ?, ?, ?)',
  ).bind(id, name, email, new Date().toISOString()).run();

  return Response.json({ id }, { status: 201 });
}

// --- Pattern-based router (strips version prefix before matching) ---

const ROUTES: Array<{
  method: string;
  pattern: RegExp;
  handler: RouteHandler;
}> = [
  {
    method: 'GET',
    pattern: /^\/users\/([^/]+)$/,
    handler: handleGetUser,
  },
  {
    method: 'POST',
    pattern: /^\/users$/,
    handler: handleCreateUser,
  },
];

function routeRequest(
  method: string,
  pathname: string,
): RouteHandler | null {
  // Strip /vN prefix before matching
  const stripped = pathname.replace(/^\/v\d+/, '');
  for (const route of ROUTES) {
    if (route.method === method && route.pattern.test(stripped)) {
      return route.handler;
    }
  }
  return null;
}

// --- Feature capabilities endpoint (alternative to version negotiation) ---

function handleCapabilities(version: Version): Response {
  return Response.json({
    version,
    features: {
      nested_profile: version >= 2,
      user_settings: version >= 3,
      streaming_responses: version >= 3,
      batch_operations: version >= 3,
    },
    deprecation: VERSION_CONFIG.deprecated.includes(version)
      ? { sunset: VERSION_CONFIG.sunset[version] }
      : null,
  });
}

// --- Main fetch handler ---

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/health') {
      return Response.json({ status: 'ok', api_version: VERSION_CONFIG.current });
    }

    const version = extractVersion(request);

    if (version === null) {
      return Response.json(
        {
          error: 'VERSION_REQUIRED',
          message: 'Specify version via URL path (/v3/…) or Accept-Version header.',
          current_version: VERSION_CONFIG.current,
        },
        { status: 400 },
      );
    }

    const minVersion = await getEffectiveMinVersion(env);
    if (version < minVersion) {
      return versionTooOldResponse(version, minVersion);
    }

    // Capabilities discovery (no further version-specific logic needed)
    if (url.pathname.replace(/^\/v\d+/, '') === '/capabilities') {
      return addVersionHeaders(handleCapabilities(version), version);
    }

    const handler = routeRequest(request.method, url.pathname);
    if (!handler) return new Response('Not found', { status: 404 });

    const response = await handler(request, env, version);
    return addVersionHeaders(response, version);
  },
};
```

## Implementation Details

**URL path vs header versioning for CDN caching:** URL path versioning includes the version in the cache key automatically. Header versioning requires `Vary: Accept-Version` in the response, and many CDN layers (including Cloudflare's default cache) do not vary on arbitrary custom headers. Prefer URL path versioning for responses you want to cache at the edge.

**Dynamic min-version via KV:** Writing `wrangler kv key put --binding KV api:min_version 3` propagates to all Worker instances worldwide within ~60 seconds. This enables raising the minimum supported version for emergency security patches without a Worker redeployment or a maintenance window.

**`/capabilities` endpoint:** Rather than hard-coding version checks in mobile clients, have the app call `/vN/capabilities` at startup and receive a feature flag map. This reduces the number of major version bumps needed — new features can be surfaced as flags even before the version is bumped.

**Deprecation header spec compliance:** `Deprecation: true` is the RFC 9512 boolean form. The `Sunset` header value must be an HTTP-date string. The `Link` header should include both `rel="deprecation"` and `rel="successor-version"` as recommended by the draft spec.

**Min-version for security patches:** When a vulnerability is patched in v3 and you need to stop serving v2 immediately: set KV key, push forced-upgrade UI to the app, then set the KV key. Coordinate the sequence: in-app prompt → KV raise → app store review. Raising the KV key before the in-app prompt is live causes silent 410 errors with no user-visible explanation.

## Anti-patterns

- Embedding major version in field names (`user_v2_id`) — version belongs in the transport layer, not in field names.
- Using semver (`/v1.2.3/`) for mobile APIs — mobile clients cannot negotiate minor versions; stick to major integers.
- Never sunsetting old versions — unbounded backward compatibility causes handler code to grow indefinitely and blocks schema changes in D1.
- Silently coercing a v1 request into v2 behavior — always echo the honored version in `X-API-Version` so clients can detect mismatches.

## Gotchas

- If a client sends a versioned URL path *and* an `Accept-Version` header with a different value, URL path takes priority (as implemented above). Document this precedence in your API reference.
- The `Deprecation` header must not be sent for current or future versions — only for versions in the `deprecated` array.
- Cloudflare's Cache API respects `Vary` on standard headers but not all custom headers. If you use header versioning, call `caches.default.match(request)` manually with a cache key that includes the version.
- When routing `/v3/users/123`, strip the version prefix before matching against route patterns, or every route pattern must repeat the version prefix.

## Verification

```bash
# URL-path versioning
curl -s https://api.example.workers.dev/v3/users/123 | jq .settings

# Header versioning
curl -s -H "Accept-Version: 2" https://api.example.workers.dev/users/123 | jq .profile

# Check deprecation headers on v1
curl -sI -H "Accept-Version: 1" https://api.example.workers.dev/users/123 | grep -i -E 'deprecation|sunset|warning'

# Raise min version via KV (emergency security patch)
wrangler kv key put --binding KV api:min_version 3
curl -sI -H "Accept-Version: 2" https://api.example.workers.dev/users/123
# → HTTP/1.1 410 Gone

# Capabilities discovery
curl -s https://api.example.workers.dev/v3/capabilities | jq .features
```

## Related

- `workers-binary-protocol-encoding.md` — content-type negotiation alongside version negotiation
- `workers-deep-link-handling.md` — version-aware deep link resolution endpoints

## Sources

- [RFC 8594 — The Sunset HTTP Header Field](https://datatracker.ietf.org/doc/html/rfc8594)
- [RFC 9512 — The Deprecation HTTP Header Field](https://datatracker.ietf.org/doc/html/rfc9512)
- [Cloudflare Workers KV — consistency](https://developers.cloudflare.com/kv/reference/how-kv-works/)
- [Cloudflare Cache API](https://developers.cloudflare.com/workers/runtime-apis/cache/)
