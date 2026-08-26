# Blue-Green Deployment for Cloudflare Workers Using KV Traffic Split

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need zero-downtime deployments for Cloudflare Workers where traffic can be instantly shifted between two live versions (blue and green) without DNS changes or cold-start delays, and you need the ability to roll back in under a second.

## Context

Cloudflare Workers does not natively support weighted traffic splitting between two versions in the same way as some platforms. The blue-green pattern solves this by running two named Workers simultaneously (`blue` and `green`) and placing a lightweight Proxy Worker in front that reads an atomic slot flag from KV to decide which backend receives each request. Promotion is a single KV write; rollback is flipping the key back.

Prerequisites:
- Two deployed Workers: `my-worker-blue` and `my-worker-green`
- A KV namespace called `DEPLOY_FLAGS`
- A Proxy Worker (this article) bound to both via service bindings

## Proxy Worker — reads KV slot and routes to active backend

```typescript
// proxy-worker/src/index.ts
import type { Env } from './env';

export interface Env {
  DEPLOY_FLAGS: KVNamespace;
  BLUE: Fetcher;   // service binding → my-worker-blue
  GREEN: Fetcher;  // service binding → my-worker-green
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Read active slot — default to 'blue' if key absent
    const slot = (await env.DEPLOY_FLAGS.get('active_slot')) ?? 'blue';

    if (slot !== 'blue' && slot !== 'green') {
      console.error(`Invalid active_slot value: ${slot}; falling back to blue`);
      return env.BLUE.fetch(request);
    }

    const backend: Fetcher = slot === 'green' ? env.GREEN : env.BLUE;

    // Forward the original request unchanged
    const response = await backend.fetch(request);

    // Stamp which slot served this response for observability
    const headers = new Headers(response.headers);
    headers.set('X-Active-Slot', slot);

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  },
};
```

## wrangler.toml — binding both service workers

```toml
# proxy-worker/wrangler.toml
name = "my-worker-proxy"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[kv_namespaces]]
binding = "DEPLOY_FLAGS"
id = "<your-kv-namespace-id>"

[[services]]
binding = "BLUE"
service = "my-worker-blue"

[[services]]
binding = "GREEN"
service = "my-worker-green"
```

## Promotion script — atomically set the active slot

```typescript
// scripts/promote.ts  (run with: npx tsx scripts/promote.ts green)
import { execSync } from 'node:child_process';

const KV_NAMESPACE_ID = process.env.KV_NAMESPACE_ID!;
const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const API_TOKEN = process.env.CLOUDFLARE_API_TOKEN!;

const target = process.argv[2] as 'blue' | 'green';
if (target !== 'blue' && target !== 'green') {
  console.error('Usage: promote.ts <blue|green>');
  process.exit(1);
}

async function smokeTest(slot: string): Promise<void> {
  const url = `https://my-worker-proxy.example.workers.dev/health`;
  // Hit proxy first, check header to confirm staging slot responds correctly
  const res = await fetch(url, { headers: { 'X-Force-Slot': slot } });
  if (!res.ok) throw new Error(`Smoke test failed: ${res.status}`);
  const body = await res.json() as { status: string };
  if (body.status !== 'ok') throw new Error(`Health check not ok: ${JSON.stringify(body)}`);
  console.log(`Smoke test passed for slot: ${slot}`);
}

async function setActiveSlot(slot: string): Promise<void> {
  const endpoint =
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${KV_NAMESPACE_ID}/values/active_slot`;
  const res = await fetch(endpoint, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
      'Content-Type': 'text/plain',
    },
    body: slot,
  });
  if (!res.ok) throw new Error(`KV write failed: ${await res.text()}`);
  console.log(`Active slot set to: ${slot}`);
}

(async () => {
  await smokeTest(target);
  await setActiveSlot(target);
  console.log(`Promotion to ${target} complete.`);
})().catch((err) => { console.error(err); process.exit(1); });
```

## Rollback — flip KV back to previous slot

Rollback is identical to promotion — just pass the other slot name:

```bash
# Promote to green
npx tsx scripts/promote.ts green

# Rollback to blue (sub-second)
npx tsx scripts/promote.ts blue
```

Because KV reads are eventually consistent, propagation across all Cloudflare PoPs takes up to 60 seconds. For truly instant global rollback, use `DEPLOY_FLAGS.put('active_slot', 'blue', { expirationTtl: 86400 })` after each write so stale reads expire quickly.

## Anti-patterns

- **Sharing KV between proxy and application code** — keep `DEPLOY_FLAGS` exclusively for deployment control; mixing it with app data makes it harder to reason about writes.
- **Deploying both slots to the same Worker name** — blue and green must be distinct Workers; renaming and redeploying is not the same as keeping two live versions.
- **Skipping smoke tests before promotion** — promote only after the new slot passes a health check to avoid flipping traffic to a broken version.
- **Reading the KV key on every sub-request** — if the proxied Worker makes internal service calls, only the proxy layer should read the slot flag.

## Gotchas

- KV is eventually consistent. After `PUT`, up to 60 s of lag is possible on cold PoPs. For latency-sensitive rollbacks, combine with a Durable Object latch for strong consistency.
- Service bindings call the Worker directly in-process — they bypass the public URL and any rate limits on that URL.
- Both `BLUE` and `GREEN` bindings must be present in `wrangler.toml` even when only one is active; removing a binding causes a deploy error.
- Workers Free plan limits may apply to the proxy Worker's KV reads (100 k/day). Check plan limits before using in high-traffic production.

## Verification

```bash
# Confirm active slot via API
curl -X GET \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/storage/kv/namespaces/$KV_NAMESPACE_ID/values/active_slot" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN"

# Confirm response header from proxy
curl -si https://my-worker-proxy.example.workers.dev/ | grep X-Active-Slot
```

## Related

- `workers-gradual-rollout-percentage-kv-feature-flag.md`
- `wrangler-environments-staging-prod-promotion.md`
- `workers-deployment-annotations-version-tags.md`

## Sources

- Cloudflare Workers Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare KV API: https://developers.cloudflare.com/kv/api/
- Wrangler configuration reference: https://developers.cloudflare.com/workers/wrangler/configuration/
