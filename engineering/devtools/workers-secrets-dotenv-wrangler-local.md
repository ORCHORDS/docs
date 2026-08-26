# Managing Secrets for Local Workers Development with `.dev.vars`

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker reads secrets (`API_KEY`, `STRIPE_SECRET`, `JWT_SECRET`) from `env` at runtime. In production these are set via `wrangler secret put`, but locally you need those values without hardcoding them, checking them into git, or running a separate secrets manager on every developer machine. Wrangler's `.dev.vars` file solves this: it is the official local-development secret mechanism, works identically to production `env` bindings, and is `.gitignore`-able.

---

## Context

Wrangler reads `.dev.vars` automatically when running `wrangler dev` (local miniflare mode). Each line is a `KEY=value` pair; the values are injected into the Worker's `env` object alongside `wrangler.toml` `[vars]` — but `.dev.vars` values take precedence over `[vars]` for the same key. The file lives at the project root beside `wrangler.toml`. It is ignored by `wrangler deploy` and `wrangler dev --remote`, so staging/production secrets are never accidentally used from it. Teams can share a `.dev.vars.example` file (secret-free) in git and distribute actual values through a secrets manager like 1Password, Doppler, or AWS Secrets Manager.

---

## Section 1 — File format and .gitignore

```bash
# .dev.vars — Wrangler reads this automatically in local dev mode
# Format: KEY=value (no quotes needed, no export keyword)
API_KEY=<redacted-secret>
STRIPE_SECRET=sk_test_51LocalDev
JWT_SECRET=local-jwt-secret-change-me-in-prod
INTERNAL_API_URL=https://staging-api.example.com

# Multi-word values with spaces — wrap in double quotes
APP_NAME="My Worker (local)"

# Empty value is valid — the key is present but env.KEY === ""
FEATURE_FLAG_NEW_UI=
```

```bash
# .gitignore — add .dev.vars (never commit real secrets)
.dev.vars

# Commit the example file instead:
# .dev.vars.example contains the same keys, values are placeholders
```

```bash
# .dev.vars.example — commit this to git
API_KEY=REPLACE_WITH_YOUR_API_KEY
STRIPE_SECRET=REPLACE_WITH_STRIPE_SECRET
JWT_SECRET=REPLACE_WITH_JWT_SECRET
INTERNAL_API_URL=https://staging-api.example.com
APP_NAME=My Worker
FEATURE_FLAG_NEW_UI=
```

```toml
# wrangler.toml — non-secret config vars live here (safe to commit)
[vars]
ENVIRONMENT = "local"
LOG_LEVEL = "debug"
# Do NOT put secrets here — they are visible in wrangler.toml plaintext
```

---

## Section 2 — TypeScript access and migration from `process.env`

```typescript
// src/types/env.ts
export interface Env {
  // Secrets set via `wrangler secret put` in production,
  // read from `.dev.vars` locally — access is identical in both cases.
  API_KEY: string;
  STRIPE_SECRET: string;
  JWT_SECRET: string;
  INTERNAL_API_URL: string;
  APP_NAME: string;
  FEATURE_FLAG_NEW_UI: string; // empty string = disabled

  // Platform bindings
  DB: D1Database;
  KV: KVNamespace;
}

// src/lib/config.ts — typed config object built from env
export interface Config {
  apiKey: string;
  stripeSecret: string;
  jwtSecret: string;
  internalApiUrl: URL;
  appName: string;
  featureNewUi: boolean;
}

export function buildConfig(env: Env): Config {
  if (!env.API_KEY) throw new Error('API_KEY is required');
  if (!env.JWT_SECRET) throw new Error('JWT_SECRET is required');

  return {
    apiKey: env.API_KEY,
    stripeSecret: env.STRIPE_SECRET,
    jwtSecret: env.JWT_SECRET,
    internalApiUrl: new URL(env.INTERNAL_API_URL || 'https://api.example.com'),
    appName: env.APP_NAME || 'My Worker',
    featureNewUi: env.FEATURE_FLAG_NEW_UI === 'true',
  };
}

// src/worker.ts
import type { Env } from '@/types/env';
import { buildConfig } from '@/lib/config';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Config is built once per request (Workers are stateless per-request)
    const config = buildConfig(env);

    // env.API_KEY works identically whether the value came from
    // .dev.vars (local), wrangler.toml [vars] (non-secret), or
    // `wrangler secret put` (production).
    const upstream = await fetch(config.internalApiUrl, {
      headers: { Authorization: `Bearer ${config.apiKey}` },
    });

    return new Response(upstream.body, {
      status: upstream.status,
      headers: { 'Content-Type': 'application/json' },
    });
  },
} satisfies ExportedHandler<Env>;
```

```typescript
// ANTI-PATTERN — never use process.env in Workers
// process.env is not available in the Workers runtime (no Node.js globals)
// This will throw at runtime even with nodejs_compat enabled for most env vars.

// ❌ Wrong
const apiKey = process.env.API_KEY; // undefined at runtime

// ✅ Correct
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const apiKey = env.API_KEY; // always defined if set in .dev.vars or wrangler secret
    // ...
  },
} satisfies ExportedHandler<Env>;
```

---

## Section 3 — Team secret distribution with Doppler

```bash
# Option A: Manual copy from 1Password / Bitwarden
# Developer copies the shared .dev.vars note content into their local file
cp .dev.vars.example .dev.vars
# Then manually fill in real values

# Option B: Doppler CLI — pulls secrets into .dev.vars format
doppler setup --project my-worker --config dev

# Export Doppler secrets as .dev.vars format (KEY=value, no quotes)
doppler secrets download --no-file --format env > .dev.vars

# Verify the file was created with the expected keys
grep -E '^[A-Z_]+=' .dev.vars | cut -d= -f1

# Option C: Automated via npm script
# package.json
# "sync-secrets": "doppler secrets download --no-file --format env > .dev.vars"
npm run sync-secrets

# Start dev with fresh secrets
npm run sync-secrets && wrangler dev
```

```bash
# Pushing a secret to production (NOT from .dev.vars — this is a separate step)
wrangler secret put API_KEY
# Prompts for the value interactively

# Or non-interactively in CI (use environment variables, not a file)
echo "$PROD_API_KEY" | wrangler secret put API_KEY

# List secrets set in production (shows names only, not values)
wrangler secret list

# Delete a production secret
wrangler secret delete OLD_SECRET_NAME
```

---

## Anti-patterns

- **Committing `.dev.vars` to git** — even in a private repo, secrets in git history are exfiltrated by repository clones, forks, and log reads. Always `.gitignore` it.
- **Using `[vars]` in `wrangler.toml` for secrets** — `[vars]` values are committed to source control in plaintext and visible to anyone with repo access; they are for non-sensitive config only.
- **Duplicating secrets in both `.dev.vars` and `wrangler.toml [vars]`** — `.dev.vars` takes precedence, but the duplication creates confusion about which value is actually used and risks committing the secret via `[vars]`.
- **Using `process.env` to access secrets** — the Workers runtime does not expose Node.js `process.env`; secrets are only accessible via the `env` parameter passed to the `fetch` handler.

---

## Gotchas

- `.dev.vars` is read **only** in local (`wrangler dev`, no `--remote` flag) mode; `wrangler dev --remote` ignores it entirely — use `--var KEY=value` for remote dev overrides.
- Values in `.dev.vars` do **not** need to be quoted, but if the value contains a `=` character you must quote it: `KEY="value=with=equals"`.
- An empty value (`KEY=`) sets `env.KEY` to an empty string `""` — not `undefined`. Check with `env.KEY !== ''` rather than `!env.KEY` if an empty string has a different meaning from absent.
- `wrangler dev` must be restarted to pick up changes to `.dev.vars`; unlike source files, it is not hot-reloaded.
- When using `nodejs_compat`, `process.env` is **partially** populated with `wrangler.toml [vars]` in some Wrangler versions — this is inconsistent and should not be relied upon; always use `env` parameter.

---

## Verification

```bash
# Confirm .dev.vars is gitignored
git check-ignore -v .dev.vars
# Expected output: .gitignore:1:.dev.vars  .dev.vars

# Confirm .dev.vars.example IS tracked
git ls-files .dev.vars.example
# Expected: .dev.vars.example

# Start local dev and hit a debug endpoint that echoes env key names
wrangler dev &
sleep 2

# If your worker exposes a debug route:
curl http://localhost:8787/__debug/env-keys

# Confirm the secret is set in production
wrangler secret list

# Verify production secret value is NOT the same as .dev.vars
# (cannot read the value back, but you can check the last-updated timestamp)
wrangler secret list | grep API_KEY
```

---

## Related

- `wrangler-dev-remote-mode-staging.md`
- `workers-typescript-path-aliases-wrangler.md`

---

## Sources

- Wrangler `.dev.vars` documentation — https://developers.cloudflare.com/workers/configuration/secrets/#local-development-with-secrets
- Wrangler secret put — https://developers.cloudflare.com/workers/wrangler/commands/#secret
- Doppler CLI — https://docs.doppler.com/docs/cli
- Cloudflare Workers environment variables — https://developers.cloudflare.com/workers/configuration/environment-variables/
