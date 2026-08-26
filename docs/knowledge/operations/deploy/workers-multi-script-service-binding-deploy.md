# Coordinated Deployment of Multiple Workers via Service Bindings

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your platform runs several Cloudflare Workers that call each other through Service Bindings. A routine deploy touches more than one service simultaneously. Without a coordination strategy you risk deploying a consumer before its provider is updated, causing runtime contract errors, unexpected 500s, or silent data corruption between services.

## Context

Cloudflare Service Bindings let one Worker invoke another over a fast in-process channel without an HTTP round-trip. The binding is declared in `wrangler.toml` as a reference to a named service. When both sides evolve independently, the caller may depend on a request/response shape that the callee no longer exposes — or vice-versa. Unlike microservice HTTP calls, there is no API gateway that can absorb the version skew; the contract is enforced only at runtime.

A safe multi-script deploy requires:
- Deploying dependency-first (providers before consumers).
- Locking the binding to a specific deployment version in `wrangler.toml`.
- Validating the integration contract between every adjacent pair of services before promoting.
- A rollback path that unwinds in reverse dependency order.

## Solution

### Step 1 — Map the dependency graph

Before writing any deploy script, enumerate every binding and draw the directed graph. Services with no inbound bindings are leaves; services depended upon by others are roots. Deploy roots first.

```
gateway-worker  →  auth-worker
                →  data-worker  →  cache-worker
```

Deploy order: `cache-worker` → `data-worker` → `auth-worker` → `gateway-worker`

### Step 2 — Version contract in `wrangler.toml`

Every consumer pins the provider to an explicit deployment version. Cloudflare does not yet expose a semver mechanism for Service Bindings, so the convention is to use a custom `X-Service-Version` header exchanged during the binding handshake, validated at runtime.

```toml
# gateway-worker/wrangler.toml
name = "gateway-worker"
main = "src/index.ts"
compatibility_date = "2025-10-01"

[[services]]
binding = "AUTH"
service = "auth-worker"

[[services]]
binding = "DATA"
service = "data-worker"
```

### Step 3 — Version handshake in TypeScript

Each worker exposes a `/version` endpoint. The consumer calls it on startup (via a warm-up request) and rejects the binding if the version is incompatible.

```typescript
// shared/version-check.ts
export const REQUIRED_AUTH_VERSION = '2.4.0';
export const REQUIRED_DATA_VERSION = '3.1.0';

export async function assertServiceVersion(
  binding: Fetcher,
  serviceName: string,
  required: string
): Promise<void> {
  const resp = await binding.fetch('https://internal/version');
  if (!resp.ok) {
    throw new Error(`${serviceName} version endpoint unreachable: ${resp.status}`);
  }
  const { version } = await resp.json<{ version: string }>();
  if (!isSemverCompatible(version, required)) {
    throw new Error(
      `${serviceName} version mismatch: got ${version}, need >= ${required}`
    );
  }
}

function isSemverCompatible(actual: string, required: string): boolean {
  const [aMaj, aMin] = actual.split('.').map(Number);
  const [rMaj, rMin] = required.split('.').map(Number);
  if (aMaj !== rMaj) return false;
  return aMin >= rMin;
}
```

```typescript
// gateway-worker/src/index.ts
import { assertServiceVersion, REQUIRED_AUTH_VERSION, REQUIRED_DATA_VERSION } from '../../shared/version-check';

export interface Env {
  AUTH: Fetcher;
  DATA: Fetcher;
}

let versionChecked = false;

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (!versionChecked) {
      await assertServiceVersion(env.AUTH, 'auth-worker', REQUIRED_AUTH_VERSION);
      await assertServiceVersion(env.DATA, 'data-worker', REQUIRED_DATA_VERSION);
      versionChecked = true;
    }

    const url = new URL(request.url);
    if (url.pathname.startsWith('/auth')) {
      return env.AUTH.fetch(request);
    }
    return env.DATA.fetch(request);
  },
};
```

### Step 4 — Ordered deploy script

```bash
#!/usr/bin/env bash
# deploy-all.sh — deploy in dependency order and abort on any failure
set -euo pipefail

SERVICES=("cache-worker" "data-worker" "auth-worker" "gateway-worker")

for svc in "${SERVICES[@]}"; do
  echo "==> Deploying $svc"
  (cd "$svc" && npx wrangler deploy --env production)
  echo "    Sleeping 5 s for propagation..."
  sleep 5
done

echo "All services deployed."
```

### Step 5 — Integration test between versions

```typescript
// tests/integration/service-binding-contract.test.ts
import { describe, it, expect, beforeAll } from 'vitest';
import { unstable_dev } from 'wrangler';
import type { UnstableDevWorker } from 'wrangler';

describe('gateway → auth binding contract', () => {
  let authWorker: UnstableDevWorker;
  let gatewayWorker: UnstableDevWorker;

  beforeAll(async () => {
    authWorker = await unstable_dev('auth-worker/src/index.ts', {
      experimental: { disableExperimentalWarning: true },
    });
    gatewayWorker = await unstable_dev('gateway-worker/src/index.ts', {
      experimental: { disableExperimentalWarning: true },
      bindings: {
        AUTH: { fetcher: authWorker },
      },
    });
  });

  it('proxies /auth/login to auth-worker and returns 200', async () => {
    const resp = await gatewayWorker.fetch('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ user: 'test', pass: 'secret' }),
      headers: { 'Content-Type': 'application/json' },
    });
    expect(resp.status).toBe(200);
    const body = await resp.json<{ token: string }>();
    expect(body.token).toBeDefined();
  });

  afterAll(async () => {
    await authWorker.stop();
    await gatewayWorker.stop();
  });
});
```

## Implementation Details

- The `versionChecked` flag resets on cold start only. In practice, warm instances skip the handshake after the first successful check, keeping request latency unaffected.
- `unstable_dev` in Vitest lets you wire real Workers together locally without Miniflare mocking.
- If a service exposes multiple API versions, model the version as a URL prefix (`/v2/`) rather than a header so wrangler's built-in routing can serve both versions simultaneously during migration.
- Pin `compatibility_date` across all services to the same date during a coordinated deploy to avoid behavioural drift from runtime API changes.

## Anti-patterns

- **Deploying consumers before providers.** The consumer will call methods that do not exist yet on the provider, producing 500s until the provider is updated.
- **Using `latest` as the binding target.** There is no `latest` concept in Service Bindings; not pinning means you rely on eventual Cloudflare propagation ordering, which is non-deterministic across PoPs.
- **Skipping the version handshake in production.** If you only check versions in tests, a mismatched deploy that passes CI will still silently break in production.
- **Parallel deploys across dependent services.** Race conditions between deploy propagation windows will cause intermittent failures during the rollout window.

## Gotchas

- Cloudflare propagates a Worker deploy to all PoPs within ~30 s, but it is not instantaneous. A 5 s sleep between sequential deploys is insufficient for a global rollout; use a smoke-test health check instead of a fixed sleep in critical paths.
- The `versionChecked` boolean is per-isolate. A new isolate spin-up (after idle eviction or a new deployment) will re-run the handshake — this is intentional and safe.
- Service Bindings bypass Cloudflare's public network, so they do not count against your Workers request egress but they do count against CPU time on the callee.
- Local `wrangler dev` currently cannot bind to a remotely deployed service unless you use `--remote`; integration tests must use `unstable_dev` to spin up both workers locally.

## Verification

1. Run `deploy-all.sh` targeting a staging environment first.
2. Execute the Vitest integration suite: `npx vitest run tests/integration/`.
3. Hit the gateway's `/version` endpoint for each downstream service and confirm versions match expected values.
4. Tail logs for 2 minutes post-deploy: `wrangler tail gateway-worker --env production`.
5. Confirm no `version mismatch` errors appear in the log stream.

## Related

- `workers-environment-promotion-pipeline.md`
- `workers-deployment-verification-smoke-tests.md`
- `workers-zero-downtime-d1-migration-deploy.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://developers.cloudflare.com/workers/wrangler/api/#unstable_dev
- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
