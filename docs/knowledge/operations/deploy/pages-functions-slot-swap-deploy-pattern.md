# Pages Functions Deployment Slot Swap Pattern

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to promote a Cloudflare Pages deployment from a preview branch to
production without downtime, rolling back instantly if smoke tests fail. The
default Pages "merge to main" flow does not let you validate the preview slot
before traffic shifts, and a bad deploy cannot be undone sub-second without a
dedicated slot-swap strategy.

## Context

Cloudflare Pages exposes every branch deployment at a deterministic URL
(`<branch>.<project>.pages.dev`). A slot swap pattern exploits this by
treating a named branch (`staging`) as a pre-production slot. The swap itself
is a Wrangler alias command that atomically redirects your custom domain to the
new deployment ID without a rebuild. Pages also supports direct-upload
deployments via the REST API, which allows scripted promotion with full
deployment-ID traceability.

---

## 1. Branch Topology Setup

```yaml
# .github/branch-protection.yml (enforced via GitHub API)
branches:
  main:        # production slot — custom domain routes here
  staging:     # staging slot — validated before swap
  feature/**:  # ephemeral preview slots
```

```toml
# wrangler.toml (Pages project config)
name = "my-app"
pages_build_output_dir = "dist"

[env.staging]
# staging branch gets its own KV / D1 bindings pointing at staging DBs
[[env.staging.kv_namespaces]]
binding = "CACHE"
id = "staging_kv_id"

[[env.production.kv_namespaces]]
binding = "CACHE"
id = "production_kv_id"
```

---

## 2. Build and Upload to Staging Slot

```typescript
// scripts/deploy-staging.ts
import { execSync } from "node:child_process";

const project = process.env.PAGES_PROJECT!;
const branch  = "staging";

function run(cmd: string): string {
  return execSync(cmd, { encoding: "utf8" }).trim();
}

// Build
run("npm run build");

// Upload to staging branch — Wrangler returns a deployment ID
const output = run(
  `wrangler pages deploy dist --project-name=${project} --branch=${branch} --commit-dirty=true`
);

const match = output.match(/deployment ID:\s+([a-f0-9-]{36})/i);
if (!match) throw new Error("Could not parse deployment ID");

const deploymentId = match[1];
console.log(`Staging deployment ID: ${deploymentId}`);
process.env.STAGING_DEPLOYMENT_ID = deploymentId;

// Persist for the swap step
run(`echo "${deploymentId}" > .staging-deployment-id`);
```

---

## 3. Smoke Tests Against the Staging Slot

```typescript
// tests/smoke/staging-slot.test.ts
import { describe, it, expect } from "vitest";

const STAGING_BASE = `https://staging.${process.env.PAGES_PROJECT}.pages.dev`;

describe("staging slot smoke tests", () => {
  it("returns 200 on /", async () => {
    const res = await fetch(STAGING_BASE);
    expect(res.status).toBe(200);
  });

  it("health endpoint reflects new build hash", async () => {
    const res  = await fetch(`${STAGING_BASE}/api/health`);
    const body = await res.json<{ buildHash: string }>();
    expect(body.buildHash).toBe(process.env.EXPECTED_BUILD_HASH);
  });

  it("critical API route responds within 300 ms", async () => {
    const t0  = Date.now();
    await fetch(`${STAGING_BASE}/api/products`);
    expect(Date.now() - t0).toBeLessThan(300);
  });
});
```

---

## 4. Slot Swap via Pages Deployments API

```typescript
// scripts/swap-slots.ts
const CF_ACCOUNT   = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN = process.env.CF_API_TOKEN!;
const PROJECT      = process.env.PAGES_PROJECT!;
const DEPLOYMENT_ID = (await import("node:fs"))
  .readFileSync(".staging-deployment-id", "utf8").trim();

// Promote staging deployment to production alias
const url = `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT}`
          + `/pages/projects/${PROJECT}/deployments/${DEPLOYMENT_ID}/retry`;

const res = await fetch(url, {
  method : "POST",
  headers: {
    Authorization : `Bearer ${CF_API_TOKEN}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ production_branch: "main" }),
});

if (!res.ok) {
  const err = await res.json();
  throw new Error(`Swap failed: ${JSON.stringify(err)}`);
}

const { result } = await res.json<{ result: { url: string } }>();
console.log(`Production now at: ${result.url}`);
```

---

## 5. Instant Rollback

```typescript
// scripts/rollback.ts
const PREVIOUS_ID = process.env.PREVIOUS_DEPLOYMENT_ID!;

// Pages API: set a deployment as the "alias" for production
const url = `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT}`
          + `/pages/projects/${PROJECT}/deployments/${PREVIOUS_ID}/retry`;

await fetch(url, {
  method : "POST",
  headers: { Authorization: `Bearer ${CF_API_TOKEN}` },
  body   : JSON.stringify({ production_branch: "main" }),
});

console.log(`Rolled back to deployment ${PREVIOUS_ID}`);
```

---

## 6. Full CI Pipeline

```yaml
# .github/workflows/deploy.yml
name: Pages Slot Swap Deploy

on:
  push:
    branches: [release/**]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to staging slot
        run: npx tsx scripts/deploy-staging.ts
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          PAGES_PROJECT: my-app

      - name: Run smoke tests
        run: npx vitest run tests/smoke/staging-slot.test.ts
        env:
          PAGES_PROJECT: my-app
          EXPECTED_BUILD_HASH: ${{ steps.build.outputs.hash }}

      - name: Swap slot to production
        if: success()
        run: npx tsx scripts/swap-slots.ts
        env:
          CF_ACCOUNT_ID:  ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN:   ${{ secrets.CF_API_TOKEN }}
          PAGES_PROJECT:  my-app

      - name: Rollback on failure
        if: failure()
        run: npx tsx scripts/rollback.ts
        env:
          CF_ACCOUNT_ID:         ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN:          ${{ secrets.CF_API_TOKEN }}
          PAGES_PROJECT:         my-app
          PREVIOUS_DEPLOYMENT_ID: ${{ steps.prev.outputs.id }}
```

---

## Anti-patterns

- **Merging to main as the deploy step** — rebuilds from scratch without a
  pre-validated staging slot; a broken build goes live immediately.
- **Using branch previews as production** — preview URLs are rate-limited and
  lack WAF/Access policies applied to the custom domain.
- **Skipping deployment ID capture** — without the ID you cannot roll back to
  the exact artifact; "redeploy last commit" may pick a different bundle if
  dependencies changed.
- **Reusing the same KV namespace across slots** — staging writes pollute
  production cache on swap; always use separate bindings per environment.

---

## Gotchas

- The Pages `/retry` endpoint clones bindings from the source deployment, not
  from `wrangler.toml`; verify binding IDs after swap in the dashboard.
- `--commit-dirty=true` is required in CI because the dist directory is not
  tracked by git; omitting it causes Wrangler to refuse the upload.
- Custom-domain propagation after a slot swap is near-instant (Cloudflare CDN
  routes by deployment alias), but any edge-cached HTML may serve stale for up
  to the configured Cache-Control TTL.
- Pages Functions bundled inside `functions/` are included in the deployment
  artifact automatically; no separate deploy step is needed for the swap.

---

## Verification

```bash
# Confirm production alias points to the new deployment ID
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/$PROJECT/deployments?env=production" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result[0] | {id, url, created_on, aliases}'

# Smoke test the live custom domain
curl -I https://app.example.com/api/health
```

---

## Related

- `cloudflare-pages-preview-deployments.md`
- `pages-middleware-versioned-deploy-strategy.md`
- `rollback-strategies-workers-pages.md`
- `wrangler-pages-direct-upload-ci.md`

---

## Sources

- Cloudflare Pages REST API — Deployments: https://developers.cloudflare.com/api/resources/pages/subresources/projects/subresources/deployments/
- Wrangler Pages deploy docs: https://developers.cloudflare.com/workers/wrangler/commands/#deploy-1
- Pages branch build controls: https://developers.cloudflare.com/pages/configuration/branch-build-controls/
