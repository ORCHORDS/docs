# Multi-Worker Local Dev with Service Bindings

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Workers project split into a main Worker and one or more dependency Workers (e.g. an `auth-service`) requires all Workers to run simultaneously during local development. Without coordinating ports and `wrangler.toml` service-binding config, the main Worker cannot reach its dependency and every cross-service call throws a fetch error.

---

## Context

Cloudflare service bindings let one Worker invoke another directly, without going through the public internet. In production, the platform routes the call internally using the bound service's name. Locally, `wrangler dev` exposes each Worker on an HTTP port, and service bindings resolve to `http://localhost:<port>` — but only when configured correctly in `wrangler.toml`. Since wrangler 3.x the `[services]` table in `wrangler.toml` accepts a `local_address` field for dev overrides. Running each Worker in a separate terminal (or via a process manager like `concurrently`) is the standard local multi-Worker pattern.

---

## Config / Setup

```toml
# wrangler.toml — main Worker (gateway)
name = "gateway"
compatibility_date = "2024-09-23"
main = "src/index.ts"

# Production service binding — resolves by name on Cloudflare's network
[[services]]
binding = "AUTH"
service = "auth-service"

# Dev override — points to the locally running auth-service Worker
# (wrangler picks up [env.dev] when `wrangler dev` is run with --env dev)
[env.dev]
[[env.dev.services]]
binding       = "AUTH"
service       = "auth-service"
local_address = "localhost:8788"  # port where auth-service listens locally
```

```toml
# workers/auth-service/wrangler.toml
name = "auth-service"
compatibility_date = "2024-09-23"
main = "src/index.ts"
```

```jsonc
// package.json — root workspace
{
  "scripts": {
    "dev"          : "concurrently -n gateway,auth -c cyan,magenta \"npm run dev:gateway\" \"npm run dev:auth\"",
    "dev:gateway"  : "wrangler dev --env dev --port 8787",
    "dev:auth"     : "wrangler dev --config workers/auth-service/wrangler.toml --port 8788"
  },
  "devDependencies": {
    "concurrently": "^8.2.2"
  }
}
```

---

## Implementation — Worker Code

```typescript
// src/index.ts — gateway Worker
export interface Env {
  AUTH: Fetcher;  // service binding type from @cloudflare/workers-types
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Forward the Authorization header to auth-service for validation
    const authResp = await env.AUTH.fetch(
      new Request('http://auth-service/validate', {
        method  : 'POST',
        headers : { authorization: request.headers.get('authorization') ?? '' },
      })
    );

    if (!authResp.ok) {
      return new Response('Unauthorized', { status: 401 });
    }

    const { userId } = await authResp.json<{ userId: string }>();
    return new Response(`Hello, ${userId}!`);
  },
} satisfies ExportedHandler<Env>;
```

```typescript
// workers/auth-service/src/index.ts
export default {
  async fetch(request: Request): Promise<Response> {
    if (new URL(request.url).pathname !== '/validate') {
      return new Response('Not found', { status: 404 });
    }

    const auth = request.headers.get('authorization') ?? '';
    if (!auth.startsWith('Bearer ')) {
      return new Response(JSON.stringify({ error: 'missing token' }), {
        status  : 401,
        headers : { 'content-type': 'application/json' },
      });
    }

    // In real code: verify JWT / lookup session
    const token  = auth.slice(7);
    const userId = `user-${token.slice(0, 8)}`;

    return new Response(JSON.stringify({ userId }), {
      headers: { 'content-type': 'application/json' },
    });
  },
} satisfies ExportedHandler;
```

```typescript
// scripts/check-services.ts — health-check all local Workers before dev starts
import { execSync } from 'node:child_process';

const SERVICES: { name: string; url: string }[] = [
  { name: 'gateway',      url: 'http://localhost:8787' },
  { name: 'auth-service', url: 'http://localhost:8788/validate' },
];

for (const svc of SERVICES) {
  try {
    execSync(`curl -sf ${svc.url} -o /dev/null`, { timeout: 2000 });
    console.log(`[ok] ${svc.name} is up`);
  } catch {
    console.warn(`[warn] ${svc.name} not responding at ${svc.url}`);
  }
}
```

---

## CI Integration

```yaml
# .github/workflows/integration.yml
name: Integration tests
on: [push, pull_request]

jobs:
  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - run: npm ci

      - name: Start auth-service in background
        run: |
          wrangler dev \
            --config workers/auth-service/wrangler.toml \
            --port 8788 --log-level warn &
          echo $! > /tmp/auth-service.pid
          # Give wrangler time to compile and listen
          sleep 5

      - name: Start gateway in background
        run: |
          wrangler dev --env dev --port 8787 --log-level warn &
          echo $! > /tmp/gateway.pid
          sleep 5

      - name: Run integration tests
        run: npx vitest run tests/integration/

      - name: Tear down Workers
        if: always()
        run: |
          kill $(cat /tmp/auth-service.pid) || true
          kill $(cat /tmp/gateway.pid)      || true
```

---

## Anti-patterns

- **Using `[services]` without `local_address` for dev** — without the override, wrangler tries to resolve the service by name on Cloudflare's network, which requires a real deployment and an API token even for local dev.
- **Running both Workers on the same port** — port collisions cause the second `wrangler dev` to fail silently or use a random port; always specify distinct `--port` values.
- **Calling `env.AUTH.fetch()` with a full external URL** — service binding fetches should use a placeholder hostname (`http://auth-service/path`); the hostname is ignored at runtime but makes the intent clear and avoids confusion with the actual URL.
- **Sharing a single `wrangler.toml` for multiple Workers** — each Worker must have its own config file so secrets, bindings, and `name` are isolated.

---

## Gotchas

- `local_address` was added in wrangler 3.22; upgrade if the field is silently ignored.
- `concurrently` exits when the first process dies; add `--kill-others-on-fail` to get clean shutdown when auth-service crashes.
- In CI, `sleep` durations depend on machine speed; prefer a polling health-check loop (`until curl -sf http://localhost:8788; do sleep 1; done`) over fixed sleeps.
- The `Fetcher` type for service bindings comes from `@cloudflare/workers-types`; without it TypeScript infers `unknown` for `env.AUTH`.
- `wrangler dev --env dev` picks up `[env.dev]` overrides from `wrangler.toml` but does **not** merge arrays — the entire `[[env.dev.services]]` block replaces `[[services]]`, so list all service bindings again under `[env.dev]` if you have more than one.

---

## Verification

```bash
# 1. Start both Workers
npm run dev

# 2. Verify auth-service responds
curl -s http://localhost:8788/validate \
  -H 'Authorization: Bearer test-token-abc123' | jq .

# 3. Verify gateway delegates to auth-service
curl -s http://localhost:8787 \
  -H 'Authorization: Bearer test-token-abc123'

# 4. Confirm binding is resolved (should NOT hit public internet)
tcpdump -i lo -nn port 8788 &
curl -s http://localhost:8787 -H 'Authorization: Bearer tok' ; kill %1
```

---

## Related

- `workers-local-dev-d1-seed-script.md`
- `eslint-workers-compatibility-lint-rules.md`

---

## Sources

- Cloudflare service bindings docs — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Wrangler services config — https://developers.cloudflare.com/workers/wrangler/configuration/#services
- concurrently npm — https://www.npmjs.com/package/concurrently
