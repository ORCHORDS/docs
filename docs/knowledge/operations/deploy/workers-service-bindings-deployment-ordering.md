# Workers Service Bindings — Deployment Ordering and Dependency Management

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You have multiple Cloudflare Workers that call each other via Service Bindings (`env.OTHER_WORKER.fetch()`). A deploy pipeline that pushes them in the wrong order — or in parallel — causes a window where the calling Worker references a binding that points to an outdated or incompatible version of the callee. In the worst case, a new callee interface ships before the caller is ready, or a caller with a changed request contract deploys before the callee can handle it.

Common failure modes:

- Parallel deploy: `worker-a` and `worker-b` deploy simultaneously; `worker-b` depends on a new method on `worker-a`, but `worker-a`'s new version hasn't propagated globally yet when `worker-b` traffic arrives.
- Reverse order: `worker-b` (caller) deploys first with new request schema; `worker-a` (callee) still runs old code that rejects the new schema.
- Rollback mismatch: rolling back `worker-a` while `worker-b` stays on the new version re-creates the incompatibility in reverse.

## Context

Service Bindings allow one Worker to invoke another via an in-process RPC or HTTP fetch with zero network egress cost and near-zero latency. Unlike a public HTTP call, the binding resolves to a specific Worker script name, not a URL. The binding is declared in `wrangler.toml`:

```toml
# worker-b/wrangler.toml
[[services]]
binding = "AUTH"        # accessed as env.AUTH inside worker-b
service = "worker-auth" # the `name` field in worker-auth/wrangler.toml
entrypoint = "AuthHandler"  # optional: named export (Workers RPC)
```

Because Service Bindings resolve by script name (not by version), they always point to the **currently deployed** version of that script. There is no pinning to a specific Worker Version via a binding. The implication: if you deploy `worker-auth` to v2 while `worker-b` is still expecting the v1 contract, all in-flight calls from `worker-b` immediately start hitting `worker-auth` v2.

## Step 1 — Classify dependencies as additive vs. breaking

Before writing a deploy order, classify each interface change:

| Change type | Example | Deploy order required |
|---|---|---|
| Additive callee | New optional field in response | Callee first, then caller |
| Additive caller | New optional request field callee ignores | Either order safe |
| Breaking callee | Removed or renamed response field | Caller deploy + callee deploy must be coordinated; see Step 3 |
| Breaking caller | New required field callee must now receive | Callee first (to accept the new field), then caller |

Enforce this classification in your PR template to catch ordering issues before merge.

## Step 2 — Establish a canonical deploy order in CI

For a three-worker graph (`worker-auth` → `worker-api` → `worker-gateway`), deploy from the leaf callee upward:

```yaml
# .github/workflows/deploy-service-chain.yml
name: Deploy Service Chain

on:
  push:
    branches: [main]

jobs:
  deploy-auth:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "npm" }
      - run: npm ci
      - name: Deploy worker-auth (callee leaf)
        working-directory: services/worker-auth
        run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
      - name: Health-check worker-auth
        run: |
          STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
            "https://worker-auth.orchords.workers.dev/health")
          [ "$STATUS" = "200" ] || exit 1

  deploy-api:
    runs-on: ubuntu-latest
    needs: deploy-auth           # wait for callee to be healthy
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "npm" }
      - run: npm ci
      - name: Deploy worker-api
        working-directory: services/worker-api
        run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

  deploy-gateway:
    runs-on: ubuntu-latest
    needs: deploy-api
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "npm" }
      - run: npm ci
      - name: Deploy worker-gateway (entry point)
        working-directory: services/worker-gateway
        run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

`needs:` serializes jobs, creating a mandatory topological ordering without coupling deploy logic inside each Worker's code.

## Step 3 — Breaking interface changes: expand-contract pattern

When a callee interface change is breaking (removes or renames a field), use a two-phase "expand-contract" deploy:

**Phase 1 — Expand (callee supports both old and new contract):**

```typescript
// worker-auth/src/index.ts — phase 1: support both response shapes
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const user = await validateToken(request, env);
    return Response.json({
      userId: user.id,       // new field name
      user_id: user.id,      // legacy field kept for backward compat
      email: user.email,
    });
  },
};
```

Deploy `worker-auth` with the expanded response. Existing `worker-api` reads `user_id` and continues working.

**Phase 2 — Migrate (callee drops old field, caller updated to new field):**

```typescript
// worker-api/src/index.ts — phase 2: caller reads new field
async function getUser(env: Env, token: string) {
  const resp = await env.AUTH.fetch(new Request("https://internal/validate", {
    headers: { Authorization: `Bearer ${token}` },
  }));
  const data = await resp.json<{ userId: string; email: string }>();
  return data.userId; // reads new field only
}
```

Deploy `worker-api` (caller) first, then redeploy `worker-auth` dropping `user_id`.

## Step 4 — Workers RPC typed interface contracts

Workers RPC (using `WorkerEntrypoint`) lets you define typed method signatures between Workers. Enforce interface compatibility with a shared TypeScript types package:

```
monorepo/
  packages/
    service-contracts/
      src/
        auth.ts        # AuthHandler interface
        payment.ts     # PaymentHandler interface
  services/
    worker-auth/       # implements AuthHandler
    worker-api/        # consumes AuthHandler
```

```typescript
// packages/service-contracts/src/auth.ts
export interface AuthHandler {
  validateToken(token: string): Promise<{ userId: string; email: string }>;
  // Breaking: removing this method requires expand-contract across both Workers
}
```

```typescript
// services/worker-auth/src/index.ts
import { WorkerEntrypoint } from "cloudflare:workers";
import type { AuthHandler } from "@example-org/example-repo/auth";

export class AuthHandlerImpl extends WorkerEntrypoint implements AuthHandler {
  async validateToken(token: string) {
    // implementation
    return { userId: "u_123", email: "user@example.com" };
  }
}
```

CI type-checks the contracts package first. A breaking change to `auth.ts` fails the type-check in `worker-api` before deploy, making ordering issues surfaced at compile time rather than runtime.

## Step 5 — Mobile app release coordination

When a mobile app (Expo / React Native) also consumes the same `worker-gateway` endpoint, coordinating the deploy order becomes three-dimensional:

1. **Callee Workers first** (worker-auth, worker-api) — same as above.
2. **worker-gateway second** — but only deploy the gateway with the new interface after checking that the current Expo OTA-live bundle does not call the removed field. Use the client-version header to gate new behavior: `request.headers.get("X-App-Version")`.
3. **Expo OTA update third** — push the new JS bundle via `eas update --branch production` only after the gateway deploy has propagated (typically within 30 seconds globally). Do not push the OTA update before the gateway is ready; the new JS bundle may call endpoints that do not yet exist.
4. **Native binary last** — native builds submitted to the App Store / Play Store should trail OTA by at least one release cycle since they cannot be recalled.

```typescript
// worker-gateway/src/index.ts — version-gated response for mobile compat
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const appVersion = request.headers.get("X-App-Version") ?? "0.0.0";
    const [major] = appVersion.split(".").map(Number);

    if (major < 3) {
      // Legacy response for app versions below 3.x still in the wild
      return legacyHandler(request, env);
    }
    return modernHandler(request, env);
  },
};
```

## Anti-patterns

- **Deploying all Workers in a monorepo in parallel**: `wrangler deploy --all` or matrix jobs without `needs:` create undefined ordering.
- **Using the caller's `wrangler.toml` to control callee behavior**: Service Bindings resolve at request time to whatever is deployed, not to what was deployed alongside the caller.
- **Skipping expand-contract and instead coordinating "fast enough"**: Sub-second propagation windows are still windows. At high traffic, some requests will hit the mismatch.
- **Testing Service Bindings only in `--local` mode**: Local simulation does not reflect the global propagation delay or the real binding resolution behavior in edge deployments.
- **Rollback order reversal**: Rolling back `worker-api` without rolling back `worker-auth` first restores the old caller against the new callee — the same incompatibility in reverse.

## Gotchas

- Service Binding calls from preview deployments (Cloudflare Pages preview branches) always hit the **production** Worker for the bound service unless the preview environment in `wrangler.toml` overrides the binding with a dedicated `environment` worker.
- `wrangler deploy` is eventually consistent globally (typically < 30 seconds). Smoke tests run immediately after deploy may briefly hit old instances in some PoPs; add a short poll with retry rather than a single-shot check.
- Cross-account Service Bindings are not supported. All bound Workers must be in the same Cloudflare account.
- A Worker that declares a binding to a non-existent script name fails at request time with a 503, not at deploy time. Validate binding targets exist before deploying the caller.
- Workers RPC currently requires both Workers to use `compatibility_date = "2024-04-03"` or later with `rpc` compatibility flag.

## Verification

```bash
# List active bindings for a deployed Worker
npx wrangler deployments list --name worker-api --env production

# Tail both Workers simultaneously and correlate by request ID
npx wrangler tail worker-auth --format json &
npx wrangler tail worker-api --format json &
# Filter correlated calls: both will share the same CF-Ray ID prefix

# Check that new binding contract is being served
curl -H "Authorization: Bearer test-token" \
  https://worker-api.orchords.workers.dev/user/me \
  | jq '.userId'   # should return string, not null
```

Run the contract type-check in CI before any deploy job:

```yaml
- name: Check service contracts compile
  run: npx tsc --project packages/service-contracts/tsconfig.json --noEmit
```

## Related

- `serverless-deploy-cloudflare-workers.md`
- `wrangler-deploy-github-actions-workers.md`
- `monorepo-deploy-pipeline-turborepo.md`
- `blue-green-deploy-cloudflare-workers.md`
- `worker-versioning-gradual-rollout.md`
- `event-schema-compat-deploys.md`

## Sources

- Cloudflare Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Workers RPC: https://developers.cloudflare.com/workers/runtime-apis/rpc/
- Wrangler services config: https://developers.cloudflare.com/workers/wrangler/configuration/#services
