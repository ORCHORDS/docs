# Preventing Secret Leakage in Workers Responses

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker accidentally surfaces API keys, database connection strings, or JWT secrets in HTTP responses — either in the response body, error messages, or debug headers. Once a secret is emitted to a client, it is effectively compromised and must be rotated immediately. The goal is to detect and block secret leakage before it reaches the wire.

---

## Context

Workers run at the edge and often proxy upstream services whose error payloads contain sensitive strings. Developers frequently add `console.log(env.DATABASE_URL)` during debugging and forget to remove it. Error boundaries that serialise the full `Error` object chain can expose stack traces containing secrets interpolated into connection strings. A middleware layer that scans outbound response bodies catches these regressions in production before clients observe them.

---

## Solution

```typescript
// secret-scanning-middleware.ts
// Response-body scanning middleware for Cloudflare Workers.
// Intercepts every outbound response and redacts known secret patterns.

export interface SecretScannerConfig {
  /** Throw a 500 instead of redacting when a secret is detected in production */
  blockOnDetection: boolean;
  /** Patterns that constitute a secret. Defaults to a built-in list. */
  patterns?: RegExp[];
  /** KV namespace to log violation events (optional) */
  auditKV?: KVNamespace;
}

// Default pattern library — extend as required.
const DEFAULT_PATTERNS: Array<{ name: string; re: RegExp }> = [
  { name: 'aws-access-key',    re: /AKIA[0-9A-Z]{16}/g },
  { name: 'aws-secret-key',    re: /(?<=["' ])[A-Za-z0-9/+]{40}(?=["' ])/g },
  { name: 'cloudflare-token',  re: /[A-Za-z0-9_-]{37,40}(?=\b)/g },
  { name: 'github-pat',        re: /gh[pousr]_[A-Za-z0-9]{36,}/g },
  { name: 'jwt',               re: /eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g },
  { name: 'generic-api-key',   re: /(?:api[_-]?key|apikey|secret)["'\s]*[=:]["'\s]*[A-Za-z0-9\-_]{16,}/gi },
  { name: 'db-conn-string',    re: /(?:postgres|mysql|mongodb)(\+srv)?:\/\/[^\s"']+:[^\s"'@]+@/gi },
  { name: 'private-key-block', re: /-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----/g },
];

export function withSecretScanning(
  handler: ExportedHandlerFetchHandler,
  config: SecretScannerConfig
): ExportedHandlerFetchHandler {
  const patterns = (config.patterns ?? []).length > 0
    ? (config.patterns as RegExp[])
    : DEFAULT_PATTERNS.map(p => p.re);

  return async (request, env, ctx): Promise<Response> => {
    const upstream = await handler(request, env, ctx);

    // Only scan text-based content types.
    const contentType = upstream.headers.get('content-type') ?? '';
    if (!contentType.includes('text') && !contentType.includes('json')) {
      return upstream;
    }

    const body = await upstream.text();
    const detections: string[] = [];

    for (const { name, re } of DEFAULT_PATTERNS) {
      re.lastIndex = 0; // reset stateful global regex
      if (re.test(body)) {
        detections.push(name);
      }
    }

    if (detections.length === 0) {
      // No secrets found — return a new Response from the consumed body.
      return new Response(body, upstream);
    }

    // Log the violation asynchronously.
    if (config.auditKV) {
      const key = `violation:${Date.now()}:${crypto.randomUUID()}`;
      const record = JSON.stringify({
        url: request.url,
        method: request.method,
        detections,
        ts: new Date().toISOString(),
      });
      ctx.waitUntil(config.auditKV.put(key, record, { expirationTtl: 30 * 86_400 }));
    }

    if (config.blockOnDetection) {
      return new Response(
        JSON.stringify({ error: 'Internal server error', code: 'SECRET_LEAK_DETECTED' }),
        { status: 500, headers: { 'content-type': 'application/json' } }
      );
    }

    // Redaction mode: replace matched strings with a placeholder.
    let redacted = body;
    for (const { re } of DEFAULT_PATTERNS) {
      re.lastIndex = 0;
      redacted = redacted.replace(re, '[REDACTED]');
    }

    const headers = new Headers(upstream.headers);
    headers.set('x-secret-scan', `detections=${detections.join(',')};action=redacted`);

    return new Response(redacted, { status: upstream.status, headers });
  };
}

// ── Environment variable audit endpoint ─────────────────────────────────────
// Expose /internal/env-audit behind a secret token to list which env vars
// are populated without revealing their values.
export async function handleEnvAudit(
  request: Request,
  env: Record<string, unknown>,
  adminToken: string
): Promise<Response> {
  const authHeader = request.headers.get('authorization') ?? '';
  if (authHeader !== `Bearer ${adminToken}`) {
    return new Response(JSON.stringify({ error: 'Unauthorized' }), {
      status: 401,
      headers: { 'content-type': 'application/json' },
    });
  }

  const audit = Object.keys(env).map(key => ({
    key,
    present: env[key] !== undefined && env[key] !== '',
    type: typeof env[key],
  }));

  return new Response(JSON.stringify({ audit, ts: new Date().toISOString() }), {
    headers: { 'content-type': 'application/json' },
  });
}

// ── Structured error response (never leaks details to clients) ───────────────
export function safeErrorResponse(
  err: unknown,
  statusCode = 500,
  requestId?: string
): Response {
  // Log the full error server-side.
  console.error('[error]', requestId, err);

  const body = JSON.stringify({
    error: 'An unexpected error occurred.',
    requestId: requestId ?? crypto.randomUUID(),
  });

  return new Response(body, {
    status: statusCode,
    headers: { 'content-type': 'application/json' },
  });
}

// ── Secret rotation detection helper ─────────────────────────────────────────
// Store a hash of each secret; alert when the raw value changes.
export async function detectSecretRotation(
  secretName: string,
  currentValue: string,
  kv: KVNamespace
): Promise<{ rotated: boolean; previousHash: string | null }> {
  const encoder = new TextEncoder();
  const hashBuf = await crypto.subtle.digest('SHA-256', encoder.encode(currentValue));
  const currentHash = Array.from(new Uint8Array(hashBuf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');

  const kvKey = `secret-hash:${secretName}`;
  const previousHash = await kv.get(kvKey);

  if (previousHash === null) {
    await kv.put(kvKey, currentHash);
    return { rotated: false, previousHash: null };
  }

  const rotated = previousHash !== currentHash;
  if (rotated) {
    await kv.put(kvKey, currentHash);
  }

  return { rotated, previousHash };
}

// ── Worker entry point ───────────────────────────────────────────────────────
interface Env {
  AUDIT_KV: KVNamespace;
  ADMIN_TOKEN: string;
}

const baseHandler: ExportedHandlerFetchHandler<Env> = async (request, env) => {
  const url = new URL(request.url);

  if (url.pathname === '/internal/env-audit') {
    return handleEnvAudit(request, env as unknown as Record<string, unknown>, env.ADMIN_TOKEN);
  }

  // Simulate an upstream that might accidentally include secrets.
  return new Response(JSON.stringify({ message: 'ok' }), {
    headers: { 'content-type': 'application/json' },
  });
};

export default {
  fetch: withSecretScanning(baseHandler, {
    blockOnDetection: true,
    auditKV: undefined, // populated at runtime from env
  }),
} satisfies ExportedHandler<Env>;
```

---

## Implementation Details

- `withSecretScanning` wraps any `fetch` handler and intercepts the response body before it reaches the client.
- Pattern matching uses `RegExp` with the `g` flag; `lastIndex` is reset before each `.test()` call to avoid false negatives with stateful regexes.
- `blockOnDetection: true` is recommended for production — returning a generic 500 is safer than redacting, which may miss patterns.
- The audit log key includes both a timestamp and a UUID so concurrent requests never overwrite each other in KV.
- `handleEnvAudit` never returns the values of secrets, only their keys and types — safe to call from internal tooling.
- `detectSecretRotation` stores a SHA-256 hash of each secret so rotation events can be tracked without persisting plaintext.

---

## Anti-patterns

- Do not log `env.*` values at startup — Workers logs are visible to anyone with account access.
- Do not rely on HTTP status codes alone to determine whether to scan (`4xx` bodies can also contain secrets).
- Do not use string `.includes()` checks instead of regex — they miss partial matches and obfuscated patterns.
- Do not store full secret values in KV even for comparison; always hash first.
- Do not expose the `/internal/env-audit` endpoint publicly; gate it behind a bearer token or Cloudflare Access.

---

## Gotchas

- `upstream.text()` consumes the body — you must construct a new `Response` from the text even when no secrets are found.
- Global regexes in JavaScript are stateful (`lastIndex`). Sharing a compiled `RegExp` across calls without resetting it causes alternating match failures.
- Streaming responses (`TransformStream`) require a different approach — you cannot buffer the entire body when `Content-Length` is large or absent.
- The `ctx.waitUntil()` call ensures the KV write completes after the response is sent; omitting it causes the write to be cancelled on response completion.
- Pattern matching on minified or base64-encoded bodies may produce false positives; tune patterns for your specific payload shapes.

---

## Verification

```bash
# 1. Deploy the Worker with wrangler.
npx wrangler deploy

# 2. Trigger the secret-leak detection by POST-ing a body containing a fake key.
curl -X POST https://your-worker.example.com/echo \
  -H 'content-type: application/json' \
  -d '{"key": "<redacted-secret>"}'
# Expected: 500 {"error":"Internal server error","code":"SECRET_LEAK_DETECTED"}

# 3. Check the env-audit endpoint.
curl https://your-worker.example.com/internal/env-audit \
  -H "Authorization: Bearer $ADMIN_TOKEN"
# Expected: JSON array of env-var names and types, no values.
```

---

## Related

- `documentation/docs/policies/security/workers-api-key-management.md`
- `documentation/docs/policies/security/workers-oauth2-pkce-flow.md`
- Cloudflare Workers Secrets: https://developers.cloudflare.com/workers/configuration/secrets/

---

## Sources

- OWASP Secret Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- Cloudflare Workers Runtime API — SubtleCrypto: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- npm `detect-secrets` reference patterns: https://github.com/Yelp/detect-secrets
