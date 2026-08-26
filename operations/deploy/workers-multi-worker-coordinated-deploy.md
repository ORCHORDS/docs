# Coordinated Deployment of Multiple Interdependent Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your system consists of multiple Cloudflare Workers that call each other — a shared utilities Worker, an API Worker that depends on it, and a BFF (Backend For Frontend) Worker that depends on the API Worker. Deploying them in the wrong order, or activating all of them simultaneously, can leave the system in a state where a new BFF calls an old API contract, causing runtime errors visible to users.

---

## Context
Cloudflare Workers can invoke each other via Service Bindings, which are resolved at deploy time by name. When Worker B depends on Worker A, Worker B must be compatible with both the *current* version of Worker A and the *next* version, enabling safe sequential deployment. The `wrangler versions upload` + `wrangler deployments create` two-phase deploy workflow lets you stage a Worker version (upload without activating traffic) and then activate it only after upstream Workers are verified. This gives you a controlled activation window and an automatic rollback path if a health check fails between steps.

---

## Section 1 — Service Bindings Configuration

```toml
# workers/shared-lib/wrangler.toml
name = "shared-lib-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[env.production]
name = "shared-lib-worker-production"
```

```toml
# workers/api/wrangler.toml
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[services]]
binding = "SHARED_LIB"
service = "shared-lib-worker-production"

[env.production]
name = "api-worker-production"
[[env.production.services]]
binding = "SHARED_LIB"
service = "shared-lib-worker-production"
```

```toml
# workers/bff/wrangler.toml
name = "bff-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[services]]
binding = "API"
service = "api-worker-production"

[env.production]
name = "bff-worker-production"
[[env.production.services]]
binding = "API"
service = "api-worker-production"
```

---

## Section 2 — Versioned Upload and Staged Activation Script

```bash
#!/usr/bin/env bash
# coordinated-deploy.sh
# Deploy order: shared-lib → api → bff
# Each step: upload version (no traffic), health check, activate version.
set -euo pipefail

WORKERS=("shared-lib" "api" "bff")
HEALTH_URLS=(
  "https://shared-lib-worker-production.workers.dev/__health"
  "https://api-worker-production.workers.dev/__health"
  "https://bff-worker-production.workers.dev/__health"
)
ROLLBACK_IDS=()   # filled as we go

health_check() {
  local url="$1" worker="$2" attempt
  for attempt in 1 2 3; do
    local status
    status=$(curl -so /dev/null -w '%{http_code}' --max-time 10 "${url}" 2>/dev/null)
    if [[ "${status}" == '200' ]]; then
      echo "  Health check passed for ${worker} (attempt ${attempt})"
      return 0
    fi
    echo "  Health check attempt ${attempt} for ${worker}: HTTP ${status}. Retrying..."
    sleep 5
  done
  echo "  Health check FAILED for ${worker} after 3 attempts."
  return 1
}

rollback_all() {
  echo "ROLLBACK: reverting all deployed Workers..."
  for i in "${!ROLLBACK_IDS[@]}"; do
    local worker="${WORKERS[$i]}"
    local prev_version="${ROLLBACK_IDS[$i]}"
    if [[ -n "${prev_version}" ]]; then
      echo "  Rolling back ${worker} to version ${prev_version}"
      cd "workers/${worker}"
      wrangler deployments create "${prev_version}" --env production || true
      cd "../.."
    fi
  done
  echo "Rollback complete."
  exit 1
}

trap rollback_all ERR

for i in "${!WORKERS[@]}"; do
  worker="${WORKERS[$i]}"
  health_url="${HEALTH_URLS[$i]}"

  echo "=== Deploying ${worker} ==="
  cd "workers/${worker}"

  # Capture current version ID for rollback
  CURRENT_VERSION=$(wrangler deployments list --env production --json 2>/dev/null \
    | jq -r '.deployments[0].version_id // empty' || echo '')
  ROLLBACK_IDS+=( "${CURRENT_VERSION}" )

  # Stage new version (no traffic yet)
  echo "  Uploading new version..."
  VERSION_ID=$(wrangler versions upload --env production --json 2>/dev/null \
    | jq -r '.version_id')
  echo "  Staged version: ${VERSION_ID}"

  # Activate staged version (100% traffic)
  echo "  Activating version..."
  wrangler deployments create "${VERSION_ID}" --env production

  cd "../.."

  # Health check before moving to the next Worker
  sleep 3   # brief propagation window
  health_check "${health_url}" "${worker}" || rollback_all

  echo "  ${worker} deployed and healthy."
done

echo "All Workers deployed successfully."
```

---

## Section 3 — Health Endpoint and GitHub Actions Integration

```typescript
// src/health.ts — shared health handler used by all Workers
export interface HealthResponse {
  ok: boolean;
  worker: string;
  version: string;
  upstreamOk?: boolean;
}

export async function handleHealth(
  workerName: string,
  version: string,
  upstreamCheck?: () => Promise<boolean>
): Promise<Response> {
  const payload: HealthResponse = {
    ok: true,
    worker: workerName,
    version,
  };

  if (upstreamCheck) {
    try {
      payload.upstreamOk = await upstreamCheck();
      payload.ok = payload.upstreamOk;
    } catch {
      payload.upstreamOk = false;
      payload.ok = false;
    }
  }

  return Response.json(payload, {
    status: payload.ok ? 200 : 503,
  });
}

// Example: bff/src/index.ts
declare const VERSION: string;

export interface Env {
  API: Fetcher;   // service binding
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/__health') {
      return handleHealth('bff-worker', VERSION, async () => {
        const res = await env.API.fetch(new Request('https://api/__health'));
        return res.ok;
      });
    }

    // ... main handler
    return env.API.fetch(request);
  },
};
```

```yaml
# .github/workflows/coordinated-deploy.yml
name: Coordinated Multi-Worker Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies (all workers)
        run: |
          for worker in shared-lib api bff; do
            (cd workers/${worker} && npm ci)
          done

      - name: Run tests
        run: |
          for worker in shared-lib api bff; do
            (cd workers/${worker} && npm test)
          done

      - name: Coordinated deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: bash scripts/coordinated-deploy.sh
```

---

## Anti-patterns
- **Deploying all Workers simultaneously** — Parallel deploys remove the health-check gate between steps; if the new API Worker breaks a contract the BFF depends on, there is no checkpoint to catch it.
- **Deploying in reverse dependency order (BFF first)** — Deploying the BFF before the shared-lib or API means the BFF may call functionality that does not yet exist in the upstream Worker.
- **Skipping `wrangler versions upload` and going straight to `wrangler deploy`** — `wrangler deploy` activates immediately with no staging window; `versions upload` lets you inspect and validate before activation.
- **Hard-coding health check URLs** — Health check targets should be derived from `wrangler.toml` or CI variables so they do not drift from actual deployed routes.

---

## Gotchas
- `wrangler versions upload` and `wrangler deployments create` are separate sub-commands introduced in Wrangler 3; older Wrangler versions use only `wrangler deploy`. Verify `wrangler --version` in CI.
- Service Bindings route requests within Cloudflare's network with no external HTTP hop; the `Fetcher` interface in TypeScript is not a standard `fetch` — it accepts a `Request` directly, not a URL string.
- A Worker referencing a Service Binding by name will fail at deploy time if the named Worker does not exist; always deploy the dependency before the dependent Worker in both staging and production.
- `wrangler deployments create <version_id>` requires the version to belong to the same Worker script; cross-worker version IDs are rejected.
- Rollback via `wrangler deployments create <prev_version_id>` restores the code but not KV or D1 state changes made by the new version — ensure data migrations are backward-compatible before deploying.

---

## Verification

```bash
# List versions for a Worker
wrangler versions list --env production --worker-name api-worker-production

# Check active deployment
wrangler deployments list --env production --worker-name bff-worker-production | head -5

# End-to-end health check across all workers
for url in \
  https://shared-lib-worker-production.workers.dev/__health \
  https://api-worker-production.workers.dev/__health \
  https://bff-worker-production.workers.dev/__health; do
  echo -n "${url}: "
  curl -sf "${url}" | jq '{ok, worker, version, upstreamOk}'
done

# Confirm service binding resolution (BFF calls API)
curl -s https://bff-worker-production.workers.dev/__health | jq '.upstreamOk'
# Expected: true
```

---

## Related
- `workers-deploy-on-git-tag-actions.md`
- `workers-zero-downtime-d1-migration-deploy.md`
- `workers-gradual-rollout-kv-percentage.md`

---

## Sources
- Cloudflare Workers Service Bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Wrangler versions and deployments commands — https://developers.cloudflare.com/workers/wrangler/commands/#versions
- Cloudflare gradual deployments documentation — https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/
