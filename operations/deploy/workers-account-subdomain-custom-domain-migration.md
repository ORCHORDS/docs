# Workers Account Subdomain to Custom Domain Migration

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Worker has been running on `my-worker.my-account.workers.dev` during development and early production. You now need to serve it on `api.example.com` without a cold-traffic gap, without changing the Worker script, and without breaking existing `workers.dev` consumers during the cutover window. DNS-only approaches cause downtime; this article documents a zero-downtime migration path with CI automation.

## Context

Cloudflare Workers support two surface areas for traffic:

- **`workers.dev` routes** — automatically provisioned at `<worker-name>.<account>.workers.dev`. Always on while the Worker is deployed.
- **Custom domain routes** — attached via `wrangler.toml` `routes` / `custom_domains` entries or the API. Require the domain to be proxied through Cloudflare (orange-clouded DNS).

The migration risk is a window where DNS has propagated to the new CNAME/A record but the Worker route is not yet active, or vice versa. The safe sequence pre-provisions the Workers route before touching DNS, then removes `workers.dev` access last.

## Step 1 — Add the Custom Domain Route Without Removing workers.dev

`wrangler.toml` supports both surface areas simultaneously. Keep `workers_dev = true` throughout the migration:

```toml
# wrangler.toml
name = "my-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

# Keep workers.dev active during cutover
workers_dev = true

# Add the new custom domain — Cloudflare provisions the TLS cert automatically
[[routes]]
pattern = "api.example.com/*"
zone_name = "example.com"
custom_domain = true
```

Deploy this configuration first. At this point both `my-api.my-account.workers.dev` and `api.example.com` resolve to the same Worker. No DNS change has been made yet; the custom domain route is provisioned inside Cloudflare's network and ready to receive traffic.

```bash
# Deploy with both surfaces active
npx wrangler deploy
```

## Step 2 — Verify the Custom Domain Route Before DNS Cut

```typescript
// scripts/verify-custom-domain.ts
async function verifyRoute(customDomain: string, expectedBody: string): Promise<void> {
  const url = `https://${customDomain}/health`;

  // Use the Cloudflare API to confirm the route is provisioned, not just that DNS resolves
  const apiToken = process.env.CLOUDFLARE_API_TOKEN!;
  const accountId = process.env.CLOUDFLARE_ACCOUNT_ID!;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/workers/scripts/my-api/routes`,
    { headers: { Authorization: `Bearer ${apiToken}` } }
  );
  const data = (await res.json()) as { result: Array<{ pattern: string }> };

  const route = data.result.find((r) => r.pattern.includes(customDomain));
  if (!route) {
    throw new Error(`Custom domain route for ${customDomain} not found in Workers API`);
  }

  // Now actually hit the endpoint (requires DNS to be pointed)
  const healthRes = await fetch(url, { headers: { 'CF-Worker-Validation': '1' } });
  if (!healthRes.ok) {
    throw new Error(`Health check failed: ${healthRes.status}`);
  }
  const body = await healthRes.text();
  if (!body.includes(expectedBody)) {
    throw new Error(`Unexpected response body: ${body}`);
  }

  console.log(`✓ Custom domain ${customDomain} is live and healthy`);
}

verifyRoute('api.example.com', '"status":"ok"').catch((e) => {
  console.error(e.message);
  process.exit(1);
});
```

## Step 3 — DNS Cutover with Gradual TTL Reduction

Before the migration deploy, reduce the DNS TTL to 60 seconds so rollback propagates quickly:

```typescript
// scripts/reduce-dns-ttl.ts
async function reduceTtl(zoneId: string, recordName: string): Promise<void> {
  const apiToken = process.env.CLOUDFLARE_API_TOKEN!;

  // Find the existing record
  const listRes = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/dns_records?name=${recordName}`,
    { headers: { Authorization: `Bearer ${apiToken}` } }
  );
  const list = (await listRes.json()) as { result: Array<{ id: string; type: string; name: string; content: string }> };

  for (const record of list.result) {
    await fetch(
      `https://api.cloudflare.com/client/v4/zones/${zoneId}/dns_records/${record.id}`,
      {
        method: 'PATCH',
        headers: {
          Authorization: `Bearer ${apiToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ ttl: 60 }),
      }
    );
    console.log(`✓ Reduced TTL to 60s for ${record.type} ${record.name}`);
  }
}

reduceTtl(process.env.ZONE_ID!, 'api.example.com');
```

Point DNS to the Cloudflare Workers CNAME (`my-api.my-account.workers.dev`) or use an orange-clouded A record that Cloudflare intercepts:

```
api.example.com  CNAME  my-api.my-account.workers.dev  (proxied, TTL: 60)
```

Because the custom domain route was pre-provisioned, traffic is routed to the Worker the moment DNS resolves — there is no gap.

## Step 4 — Disable workers.dev After Cutover Confirmation

Once monitoring confirms the custom domain is handling traffic correctly, remove the `workers.dev` surface to prevent split-traffic confusion and enforce a single ingress:

```toml
# wrangler.toml — after cutover confirmed
name = "my-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

# Disable workers.dev access
workers_dev = false

[[routes]]
pattern = "api.example.com/*"
zone_name = "example.com"
custom_domain = true
```

```bash
# Re-deploy to disable workers.dev
npx wrangler deploy
```

## CI Pipeline for the Full Migration

```yaml
# .github/workflows/domain-migration.yml
name: Domain Migration

on:
  workflow_dispatch:
    inputs:
      phase:
        description: 'Migration phase: provision | verify | cutover | finalize'
        required: true

jobs:
  migrate:
    runs-on: ubuntu-latest
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
      ZONE_ID: ${{ secrets.CF_ZONE_ID }}

    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: npm ci

      - name: Phase — Provision custom domain route
        if: inputs.phase == 'provision'
        run: |
          # Deploy with workers_dev=true and custom_domain route
          npx wrangler deploy --config wrangler.migrate-provision.toml

      - name: Phase — Verify route
        if: inputs.phase == 'verify'
        run: npx tsx scripts/verify-custom-domain.ts

      - name: Phase — DNS cutover (reduce TTL)
        if: inputs.phase == 'cutover'
        run: npx tsx scripts/reduce-dns-ttl.ts

      - name: Phase — Finalize (disable workers.dev)
        if: inputs.phase == 'finalize'
        run: |
          npx wrangler deploy --config wrangler.toml
          echo "workers.dev disabled. Custom domain is sole ingress."
```

## Anti-patterns

- **Pointing DNS before the Workers route is provisioned** — causes a gap where DNS resolves but no Worker handles the request, producing 522 errors.
- **Disabling `workers_dev` and adding the custom domain in the same deploy** — if route provisioning fails mid-deploy, the Worker temporarily has no accessible route.
- **Using a non-proxied (grey-cloud) DNS record** — Cloudflare cannot intercept the traffic, so custom domain Workers routing does not apply. The record must be orange-clouded.
- **Forgetting to update `wrangler.toml` in source control after finalization** — the next deploy by a developer with a stale config re-enables `workers.dev`.

## Gotchas

- TLS certificate provisioning for a new `custom_domain = true` entry can take up to 60 seconds after deploy. The verify step should retry with backoff rather than failing immediately.
- If the zone is on a Business or Enterprise plan with custom certificates, `custom_domain = true` in `wrangler.toml` may conflict. Use `routes` with explicit `zone_id` instead.
- Workers `workers.dev` routes count against the same script size and CPU limits as custom domain routes — disabling `workers.dev` does not change resource limits, only access surface.
- A Worker script that reads `request.url` will see `https://my-api.my-account.workers.dev/...` during the `workers.dev` phase and `https://api.example.com/...` after cutover. If your Worker constructs absolute URLs or sets CORS `origin` headers based on `request.url`, test both paths.

## Verification

```bash
# Confirm workers.dev is disabled after finalization
curl -I https://my-api.my-account.workers.dev/health 2>&1 | grep "HTTP/"
# Expected: HTTP/1.1 404 or connection refused

# Confirm custom domain is live
curl -I https://api.example.com/health 2>&1 | grep "HTTP/"
# Expected: HTTP/2 200

# Check CF-Ray header to confirm traffic is hitting the Worker
curl -si https://api.example.com/health | grep -i "cf-ray"
```

## Related

- `pages-custom-domain-ssl-deploy-automation.md`
- `wrangler-environments-promotion-pipeline.md`
- `cloudflare-workers-deploy-pipeline.md`
- `workers-service-bindings-deployment-ordering.md`

## Sources

- Cloudflare Workers custom domains: https://developers.cloudflare.com/workers/configuration/routing/custom-domains/
- Wrangler routes configuration: https://developers.cloudflare.com/workers/wrangler/configuration/#routes
- Workers `workers_dev` setting: https://developers.cloudflare.com/workers/wrangler/configuration/#workers_dev
