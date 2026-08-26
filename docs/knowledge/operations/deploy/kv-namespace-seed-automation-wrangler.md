# KV Namespace Deploy Seed Automation with Wrangler

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

After deploying a new Worker, configuration keys that live in KV must be populated before the Worker can serve real traffic. Engineers are either seeding KV by hand — causing races between the deploy job and first requests — or duplicating seed logic across multiple CI pipelines with no idempotency guarantees.

## Context

KV namespace seeding is a deploy-time side effect that must be **idempotent**, **ordered** (seed before traffic), and **environment-aware** (staging vs production namespaces are different). This article covers a structured seeding pattern: a typed seed manifest, a Wrangler-based bulk-write script, and a CI step that gates traffic promotion on seed completion.

---

## 1. Seed Manifest Schema

Define seed data as a version-controlled JSON file per environment:

```jsonc
// config/kv-seed.staging.json
{
  "feature:new-checkout":    "false",
  "feature:dark-mode":       "true",
  "config:max-cart-items":   "50",
  "config:currency":         "USD",
  "rate-limit:global-rps":   "1000",
  "maintenance-mode":        "false"
}
```

```jsonc
// config/kv-seed.production.json
{
  "feature:new-checkout":    "false",
  "feature:dark-mode":       "true",
  "config:max-cart-items":   "100",
  "config:currency":         "USD",
  "rate-limit:global-rps":   "5000",
  "maintenance-mode":        "false"
}
```

---

## 2. Idempotent Seed Script

The script uses the KV REST API's bulk write endpoint and **does not overwrite** keys that already exist (use `--force` to override):

```typescript
// scripts/kv-seed.ts
import { readFileSync } from "node:fs";
import { resolve }      from "node:path";

const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN  = process.env.CF_API_TOKEN!;
const NS_ID      = process.env.KV_NAMESPACE_ID!;
const ENV        = process.env.DEPLOY_ENV ?? "staging";
const FORCE      = process.argv.includes("--force");

interface KVBulkItem {
  key:         string;
  value:       string;
  expiration?: number;
  metadata?:   Record<string, string>;
}

async function listExistingKeys(): Promise<Set<string>> {
  const existing = new Set<string>();
  let cursor: string | undefined;

  do {
    const url = new URL(
      `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${NS_ID}/keys`
    );
    if (cursor) url.searchParams.set("cursor", cursor);

    const res  = await fetch(url, { headers: { Authorization: `Bearer ${API_TOKEN}` } });
    const data = await res.json() as any;

    for (const item of data.result ?? []) existing.add(item.name);
    cursor = data.result_info?.cursor;
  } while (cursor);

  return existing;
}

async function bulkWrite(items: KVBulkItem[]): Promise<void> {
  if (items.length === 0) { console.log("Nothing to seed."); return; }

  // KV bulk write is capped at 10 000 items per request
  const CHUNK = 10_000;
  for (let i = 0; i < items.length; i += CHUNK) {
    const chunk = items.slice(i, i + CHUNK);
    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${NS_ID}/bulk`,
      {
        method:  "PUT",
        headers: {
          Authorization:  `Bearer ${API_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(chunk),
      }
    );
    const data = await res.json() as any;
    if (!data.success) throw new Error(`Bulk write failed: ${JSON.stringify(data.errors)}`);
    console.log(`Seeded chunk ${i / CHUNK + 1}: ${chunk.length} keys`);
  }
}

async function main() {
  const manifestPath = resolve(`config/kv-seed.${ENV}.json`);
  const manifest: Record<string, string> = JSON.parse(readFileSync(manifestPath, "utf8"));

  const existingKeys = FORCE ? new Set<string>() : await listExistingKeys();

  const toWrite: KVBulkItem[] = Object.entries(manifest)
    .filter(([key]) => FORCE || !existingKeys.has(key))
    .map(([key, value]) => ({
      key,
      value,
      metadata: { seeded_at: new Date().toISOString(), env: ENV },
    }));

  console.log(
    `Seeding ${toWrite.length} of ${Object.keys(manifest).length} keys` +
    (FORCE ? " (force mode — overwriting all)" : " (skipping existing keys)")
  );

  await bulkWrite(toWrite);
  console.log("KV seed complete.");
}

main().catch(err => { console.error(err); process.exit(1); });
```

---

## 3. Wrangler Direct Upload Alternative (Small Manifests)

For small manifests (< 50 keys), use `wrangler kv bulk put` with the JSON format:

```bash
# scripts/seed-kv-wrangler.sh
set -euo pipefail

ENV="${DEPLOY_ENV:-staging}"
MANIFEST="config/kv-seed.${ENV}.json"

# Convert object to Wrangler bulk array: [{key, value}, ...]
BULK_JSON=$(jq '[to_entries[] | {key: .key, value: .value}]' "$MANIFEST")

echo "$BULK_JSON" | wrangler kv bulk put \
  --namespace-id "$KV_NAMESPACE_ID" \
  -                                         # read from stdin

echo "KV seed via Wrangler complete for env: ${ENV}"
```

---

## 4. CI Pipeline — Seed Before Traffic Promotion

```yaml
# .github/workflows/deploy.yml
name: Deploy Worker + Seed KV

on:
  push:
    branches: [main, staging]

env:
  DEPLOY_ENV: ${{ github.ref_name == 'main' && 'production' || 'staging' }}

jobs:
  deploy-and-seed:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci

      # 1. Deploy Worker code
      - name: Deploy Worker
        run: npx wrangler deploy --env "$DEPLOY_ENV"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      # 2. Seed KV BEFORE health check and traffic promotion
      - name: Seed KV namespace
        run: npx tsx scripts/kv-seed.ts
        env:
          CF_ACCOUNT_ID:    ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN:     ${{ secrets.CF_API_TOKEN }}
          KV_NAMESPACE_ID:  ${{ secrets[format('KV_NS_ID_{0}', env.DEPLOY_ENV)] }}
          DEPLOY_ENV:       ${{ env.DEPLOY_ENV }}

      # 3. Health check — Worker reads seeded keys
      - name: Smoke test
        run: |
          URL="${{ env.DEPLOY_ENV == 'production' && 'https://myapp.com' || 'https://staging.myapp.com' }}"
          STATUS=$(curl -sf -o /dev/null -w "%{http_code}" "$URL/health")
          [ "$STATUS" = "200" ] || { echo "Health check failed: $STATUS"; exit 1; }
```

---

## 5. Seed Drift Detection

Run seed drift detection as a post-deploy verification step to surface keys that exist in production but not in the manifest (leftover from old features):

```typescript
// scripts/kv-drift-check.ts
import { readFileSync } from "node:fs";
import { resolve }      from "node:path";

const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN  = process.env.CF_API_TOKEN!;
const NS_ID      = process.env.KV_NAMESPACE_ID!;
const ENV        = process.env.DEPLOY_ENV ?? "staging";

async function main() {
  const manifest: Record<string, string> = JSON.parse(
    readFileSync(resolve(`config/kv-seed.${ENV}.json`), "utf8")
  );
  const manifestKeys = new Set(Object.keys(manifest));

  // Fetch live keys (simplified — add pagination for large namespaces)
  const res  = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${NS_ID}/keys?limit=1000`,
    { headers: { Authorization: `Bearer ${API_TOKEN}` } }
  );
  const data = await res.json() as any;
  const liveKeys: string[] = data.result.map((k: any) => k.name);

  const orphaned = liveKeys.filter(k => !manifestKeys.has(k));
  if (orphaned.length > 0) {
    console.warn("Orphaned KV keys (not in manifest):", orphaned);
    // Fail CI if desired: process.exit(1);
  } else {
    console.log("No orphaned keys found.");
  }
}

main().catch(err => { console.error(err); process.exit(1); });
```

---

## Anti-patterns

- **Seeding KV after traffic promotion** — the Worker may receive requests before config keys exist, causing null-reference errors or feature flags defaulting to unsafe values.
- **Using `wrangler kv key put` in a loop** — N sequential API calls take N × ~100 ms; the bulk write endpoint handles 10 000 keys in a single request.
- **Hardcoding namespace IDs in scripts** — use environment variables or Wrangler bindings to keep the script environment-agnostic.
- **Mutating seed values in production without a manifest update** — manual KV edits drift from the manifest; the drift-detection script surfaces these.

## Gotchas

- **KV consistency** — after a bulk write, new values propagate globally within ~60 s under eventual consistency. If the Worker reads immediately after seeding and gets a cold start, it may see stale values. Add a 10 s sleep or re-read the health endpoint until all seed keys resolve.
- **Bulk write response** — the `PUT /bulk` endpoint returns `{"success": true, "result": null}` on success. A `4xx` response body contains the specific key that failed (e.g., value exceeds 25 MB limit).
- **Metadata size** — KV metadata is limited to 1024 bytes. Do not store large objects in the `metadata` field; use the value field instead.
- **Pagination in drift detection** — the Keys list endpoint returns at most 1000 keys per page; add cursor-based pagination for namespaces with > 1000 keys.

## Verification

```bash
# List seeded keys
wrangler kv key list --namespace-id "$KV_NAMESPACE_ID" | jq '.[].name'

# Spot-check a specific key
wrangler kv key get "feature:new-checkout" --namespace-id "$KV_NAMESPACE_ID"

# Run drift detection
CF_ACCOUNT_ID="$CF_ACCOUNT_ID" \
CF_API_TOKEN="$CF_API_TOKEN" \
KV_NAMESPACE_ID="$KV_NAMESPACE_ID" \
DEPLOY_ENV="production" \
npx tsx scripts/kv-drift-check.ts
```

## Related

- `feature-flag-deploy-coupling.md`
- `feature-flag-deployment-gates-cloudflare-kv.md`
- `workers-kv-namespace-migration-deploy.md`
- `env-binding-precedence.md`

## Sources

- KV Bulk Write API: https://developers.cloudflare.com/api/resources/kv/subresources/namespaces/subresources/bulk/methods/create/
- Wrangler KV commands: https://developers.cloudflare.com/workers/wrangler/commands/#kv
- KV limits: https://developers.cloudflare.com/kv/platform/limits/
