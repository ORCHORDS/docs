# Workers Environment Variable Hygiene

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

A Cloudflare Worker is deployed with API keys, database credentials, and signing secrets. Weeks later a developer discovers that:

- The `wrangler.toml` committed to the repository contains plaintext values in `[vars]` that were "just for testing" but are the production values.
- An error handler returns the full `env` object in a JSON response, leaking every binding name and value.
- A debug route prints `JSON.stringify(env)` to help a developer, but that route is not access-controlled.
- A console log statement inside a Worker reads `env.DB_PASSWORD` directly, which appears verbatim in Cloudflare logpush exports shared with a third-party logging provider.

This article covers the operational patterns that prevent each of these failure modes.

---

## Context

Cloudflare Workers have three categories of runtime bindings:

| Category | Examples | Serialisable? |
|---|---|---|
| **Plain vars** | `[vars]` in `wrangler.toml` | Yes — strings; visible in `wrangler.toml` source |
| **Secrets** | `wrangler secret put` or dashboard Secrets | No — opaque; never appear in logs or exports by design |
| **Resource bindings** | KV, D1, DO, R2, Service bindings | No — objects/stubs; not serialisable |

The critical distinction: `[vars]` values are plaintext strings that appear in `wrangler.toml`, in the Cloudflare dashboard, and in your git history. `wrangler secret` values are encrypted at rest, excluded from source control, and **not available as plaintext even to Cloudflare support**. Secrets are the correct mechanism for any value you would not want visible in a bug report.

---

## Separating Secrets from Config in wrangler.toml

```toml
# wrangler.toml — commit this file
name = "my-api"
main = "src/worker.ts"
compatibility_date = "2026-01-01"

# NON-SECRET config: feature flags, log levels, timeout values
[vars]
LOG_LEVEL = "info"
REQUEST_TIMEOUT_MS = "5000"
ENVIRONMENT = "production"
CORS_ALLOWED_ORIGIN = "https://app.example.com"

# NEVER put the following in [vars]:
# DATABASE_URL, API_KEY, JWT_SECRET, SIGNING_SECRET, OAUTH_CLIENT_SECRET
#
# Instead, use:
#   wrangler secret put DATABASE_URL
#   wrangler secret put API_KEY
#   wrangler secret put JWT_SECRET

# Resource bindings are safe — they are object references, not values
[[d1_databases]]
binding = "DB"
database_name = "production-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[kv_namespaces]]
binding = "SESSION_KV"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

```bash
# Deploy all secrets once (CI/CD pipeline or initial setup)
# These are encrypted and stored in Cloudflare's secret store
wrangler secret put DATABASE_URL   # prompts for value, or pipe via stdin
wrangler secret put API_KEY
wrangler secret put JWT_SECRET
wrangler secret put SIGNING_SECRET

# Verify secrets are registered (values are never printed)
wrangler secret list
# Output:
# NAME            CREATED AT
# DATABASE_URL    2026-08-22T10:00:00Z
# API_KEY         2026-08-22T10:01:00Z
# JWT_SECRET      2026-08-22T10:01:30Z
```

---

## TypeScript Env Interface: Making Secrets Explicit

Define the `Env` interface so TypeScript enforces that secrets exist and prevents accidental misuse of plain vars as secrets:

```typescript
// src/types/env.ts

export interface Env {
  // ---- NON-SECRET CONFIG (wrangler.toml [vars]) ----
  LOG_LEVEL: string;
  REQUEST_TIMEOUT_MS: string;
  ENVIRONMENT: 'production' | 'staging' | 'development';
  CORS_ALLOWED_ORIGIN: string;

  // ---- SECRETS (wrangler secret put) ----
  // TypeScript type is the same (string), but naming convention and
  // documentation mark these as secrets. Document with JSDoc.

  /** @secret Encrypted via wrangler secret put. Never log or return in responses. */
  DATABASE_URL: string;

  /** @secret JWT signing key (HS256). Min 256-bit entropy. */
  JWT_SECRET: string;

  /** @secret External payment API key. Rotate via wrangler secret put. */
  API_KEY: string;

  // ---- RESOURCE BINDINGS ----
  DB: D1Database;
  SESSION_KV: KVNamespace;
}
```

---

## Never Serialise the Env Object

The most common accidental leak is `JSON.stringify(env)` or `return Response.json({ env })` in an error handler.

```typescript
// src/middleware/error-handler.ts
import type { Env } from '../types/env';

// BAD: leaks all binding names and plain var values
function badErrorHandler(err: Error, env: Env): Response {
  return Response.json({
    error: err.message,
    env,              // ← leaks CORS_ALLOWED_ORIGIN, LOG_LEVEL, etc.
    // Secrets (DATABASE_URL, JWT_SECRET) are not serialisable, but
    // their *binding names* still appear as null/undefined keys.
  });
}

// GOOD: return only a safe error envelope
export function safeErrorResponse(err: Error, env: Env): Response {
  const isDev = env.ENVIRONMENT !== 'production';

  // In production: never expose internal details
  // In dev: show message but not env
  const body = {
    error: isDev ? err.message : 'Internal server error',
    requestId: crypto.randomUUID(), // correlate with internal logs
    ...(isDev && { stack: err.stack }),
    // Never include: env, err.cause if it contains credentials
  };

  return Response.json(body, { status: 500 });
}
```

---

## Safe Logging: Redacting Secrets from Log Lines

```typescript
// src/lib/logger.ts
import type { Env } from '../types/env';

const SECRET_BINDING_NAMES = new Set([
  'DATABASE_URL',
  'JWT_SECRET',
  'API_KEY',
  'SIGNING_SECRET',
]);

/**
 * Log a message to the Cloudflare Workers runtime console.
 * Objects are JSON-serialised with secret fields redacted.
 *
 * Note: console.log output appears in:
 *   - wrangler tail (local dev)
 *   - Cloudflare logpush exports (production)
 * Never log raw secret values. This helper enforces that.
 */
export function log(
  level: 'info' | 'warn' | 'error',
  message: string,
  data?: Record<string, unknown>
): void {
  if (!data) {
    consolelevel;
    return;
  }

  const sanitised = Object.fromEntries(
    Object.entries(data).map(([k, v]) => [
      k,
      SECRET_BINDING_NAMES.has(k) ? '[REDACTED]' : v,
    ])
  );

  consolelevel);
}

// Usage:
// log('info', 'Request processed', { userId: '123', path: '/api/data' });
// log('error', 'DB error', { DATABASE_URL: env.DATABASE_URL }); // DATABASE_URL → [REDACTED]
```

---

## Audit: Listing All Bindings a Worker Has Access To

Before production deployment, audit what the Worker can access:

```bash
# List all secrets bound to the Worker
wrangler secret list --name my-api

# Show the full deployed Worker config (no secret values, only names)
wrangler deployments view --name my-api

# Use wrangler types to regenerate the Env interface from actual bindings
# and diff against your manually maintained src/types/env.ts
wrangler types --output-path .wrangler/types/env.d.ts
diff src/types/env.ts .wrangler/types/env.d.ts
```

---

## CI/CD: Injecting Secrets via Environment Variables

In CI pipelines (GitHub Actions, etc.), secrets are passed as environment variables. The `wrangler` CLI reads `CLOUDFLARE_API_TOKEN` for authentication. Never hard-code the Cloudflare API token.

```yaml
# .github/workflows/deploy.yml
name: Deploy Worker

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy Worker
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          # NOTE: Do NOT pass application secrets here. They are already
          # registered in Cloudflare's secret store via wrangler secret put.
          # The only secret needed at deploy time is the API token.

      # If you need to update an application secret in CI:
      - name: Rotate API Key
        if: github.event_name == 'workflow_dispatch'
        run: echo "${{ secrets.NEW_API_KEY }}" | wrangler secret put API_KEY
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

---

## Preventing Secret Reflection via Request Headers

A subtle leak: copying all request headers into a downstream fetch call, where those headers might include `Authorization` sent to an unintended recipient:

```typescript
// BAD: forwards Authorization and any debug headers to a third-party
async function badProxyFetch(request: Request, env: Env): Promise<Response> {
  return fetch('https://third-party.example.com/api', {
    headers: request.headers, // blindly forwards credentials
  });
}

// GOOD: explicitly allowlist headers to forward
const SAFE_HEADERS_TO_FORWARD = ['Accept', 'Content-Type', 'Accept-Language'];

async function safeProxyFetch(request: Request, env: Env): Promise<Response> {
  const outboundHeaders = new Headers();

  for (const name of SAFE_HEADERS_TO_FORWARD) {
    const value = request.headers.get(name);
    if (value) outboundHeaders.set(name, value);
  }

  // Add outbound auth using a secret, not the caller's token
  outboundHeaders.set('X-Api-Key', env.API_KEY);

  return fetch('https://third-party.example.com/api', {
    method: request.method,
    headers: outboundHeaders,
    body: request.body,
  });
}
```

---

## Anti-patterns

**Putting secrets in `[vars]` "temporarily".** There is no safe temporary plaintext secret. Once a value is in `wrangler.toml` and committed, it is in git history permanently. Use `git-filter-repo` to scrub it and rotate the secret immediately.

**Using separate `wrangler.toml` files per environment with secrets in the staging file.** Staging `[vars]` with real credentials are still plaintext in source control. Use `wrangler.toml` for non-secret config and `wrangler secret put --env staging` for all secrets.

**Logging `env.DATABASE_URL` to debug a connection issue.** Instead log only the host portion: `new URL(env.DATABASE_URL).hostname`. Never log passwords.

**Returning the full `Error` object from a Worker.** `Error` objects often contain context objects that include credentials passed to database drivers or HTTP clients. Sanitise errors before returning them.

**Sharing Cloudflare API tokens across projects.** A compromised token with `Workers: edit` on all Workers can read or overwrite any secret. Scope API tokens to the minimum required resource via Cloudflare's API token permissions editor.

---

## Gotchas

**`wrangler secret` values are not available in `wrangler dev` by default.** In local development, `wrangler dev` reads `.dev.vars` (gitignored) instead of the Cloudflare secret store. Ensure `.dev.vars` is listed in `.gitignore` and never committed.

**`wrangler types` generates types from deployed bindings, not source.** If you add a new secret but haven't deployed yet, `wrangler types` won't show it. Maintain `src/types/env.ts` manually in sync with your secrets and update it as part of your secret-addition checklist.

**Cloudflare logpush exports include `console.log` output.** If you pipe logs to a third-party SIEM (Datadog, Splunk), all `console.log` output goes there. Ensure your log redaction middleware runs on every log call — not just in the error handler.

**Secrets bound as plain string values are not Opaque in TypeScript.** The `Env.JWT_SECRET: string` type does not prevent `Response.json({ secret: env.JWT_SECRET })`. TypeScript nominal typing via branded types (`type JwtSecret = string & { readonly __brand: 'JwtSecret' }`) can add a layer of friction but requires discipline to maintain.

**`wrangler secret list` does not verify values are correct — only that a binding exists.** After rotation, test the new secret by hitting a staging endpoint that exercises the binding, not just by checking the list output.

---

## Verification

```bash
# 1. Grep wrangler.toml for any value that looks like a secret
grep -Ei '(key|secret|password|token|credential|auth).*=.*[A-Za-z0-9+/]{20,}' wrangler.toml
# Any match should be investigated and moved to wrangler secret put

# 2. Grep source code for unsafe env serialisation patterns
grep -rn 'JSON.stringify(env)' src/
grep -rn 'return.*env' src/
grep -rn 'console.log.*env\.' src/

# 3. Verify .dev.vars is gitignored
git check-ignore -v .dev.vars
# Expected: .gitignore:<line>:.dev.vars  .dev.vars

# 4. Confirm no secrets in git history
git log --all --full-history -- .dev.vars
# Expected: empty (file should never have been committed)

# 5. Run wrangler tail and verify no secret values appear in live logs
wrangler tail --format pretty
# Trigger a request and visually inspect the output
```

---

## Related

- `api-key-rotation-workers-kv-secrets.md` — rotating secrets stored in KV
- `api-key-rotation-zero-downtime.md` — zero-downtime secret rotation patterns
- `secrets-detection-pre-commit.md` — git pre-commit hooks to block secret commits
- `gitleaks-cloudflare-webhook.md` — automated secret scanning on push
- `git-history-secret-removal.md` — removing committed secrets from git history
- `audit-log-security.md` — what to include in audit logs without leaking secrets

---

## Sources

- Cloudflare Workers Secrets documentation: https://developers.cloudflare.com/workers/configuration/secrets/
- `wrangler secret` CLI reference: https://developers.cloudflare.com/workers/wrangler/commands/#secret
- Cloudflare API Token permissions: https://developers.cloudflare.com/fundamentals/api/get-started/create-token/
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- `.dev.vars` local development guide: https://developers.cloudflare.com/workers/configuration/environment-variables/#local-development-with-dev-vars
