# GitHub Actions Workers KV Namespace Seeding and Teardown for Preview Environments

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Preview environments for Cloudflare Workers that depend on KV data start cold — no fixtures — causing integration tests to fail or UI previews to show empty states. You need a repeatable way to seed KV namespaces per PR branch, bind them to the preview worker, and delete them when the PR closes.

## Context

Wrangler exposes `kv:key put` and `kv:bulk put` for scripted writes. Combined with the Cloudflare REST API (`/kv/namespaces`) you can create an ephemeral namespace per PR, seed it from a JSON fixture file checked into the repo, bind it via a `wrangler.toml` override, deploy the preview worker, then delete the namespace on PR close. Unlike D1 — which has `wrangler d1 execute` for migrations — KV has no schema concept, so seed data is raw JSON key/value pairs.

## Step 1 — Create a per-PR KV Namespace

```yaml
# .github/workflows/preview-kv-seed.yml
name: Preview – seed KV
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  seed:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    outputs:
      kv_namespace_id: ${{ steps.create_ns.outputs.kv_namespace_id }}
    steps:
      - uses: actions/checkout@v4

      - name: Create ephemeral KV namespace
        id: create_ns
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          NS_TITLE="pr-${{ github.event.number }}-preview-kv"
          RESPONSE=$(curl -s -X POST \
            "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/json" \
            --data "{\"title\":\"${NS_TITLE}\"}")
          KV_ID=$(echo "$RESPONSE" | jq -r '.result.id')
          echo "kv_namespace_id=${KV_ID}" >> "$GITHUB_OUTPUT"
          echo "Created KV namespace: ${KV_ID}"
```

## Step 2 — Bulk-Seed KV from a Fixture File

```typescript
// scripts/build-kv-seed.ts
// Converts fixtures/kv-seed.json to Wrangler bulk-put format
import seedData from "../fixtures/kv-seed.json" assert { type: "json" };

const bulk = Object.entries(seedData).map(([key, value]) => ({
  key,
  value: typeof value === "string" ? value : JSON.stringify(value),
  expiration_ttl: undefined, // omit for no expiry
}));

process.stdout.write(JSON.stringify(bulk));
```

```yaml
      - name: Seed KV namespace
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          npx tsx scripts/build-kv-seed.ts > /tmp/kv-bulk.json
          curl -s -X PUT \
            "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${{ steps.create_ns.outputs.kv_namespace_id }}/bulk" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/json" \
            -d @/tmp/kv-bulk.json | jq '.success'
```

## Step 3 — Inject Namespace Binding into Wrangler and Deploy

```yaml
      - name: Deploy preview worker with KV binding
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          # Override kv_namespaces binding without editing wrangler.toml
          npx wrangler deploy \
            --name "pr-${{ github.event.number }}-preview" \
            --env preview \
            --var KV_NAMESPACE_ID:${{ steps.create_ns.outputs.kv_namespace_id }}
```

> If your `wrangler.toml` uses `[[kv_namespaces]]`, inject via `WRANGLER_TOML` override or patch the file with `sed` before deploy.

## Step 4 — Store Namespace ID for Teardown

```yaml
      - name: Persist namespace ID to env
        uses: actions/github-script@v7
        with:
          script: |
            await github.rest.repos.createOrUpdateEnvironmentVariable({
              owner: context.repo.owner,
              repo: context.repo.repo,
              environment_name: `pr-${context.payload.number}`,
              name: 'KV_NAMESPACE_ID',
              value: '${{ steps.create_ns.outputs.kv_namespace_id }}'
            });
```

Alternatively, write the ID to a PR comment or a workflow artifact so the teardown job can retrieve it.

## Step 5 — Teardown on PR Close

```yaml
name: Preview – teardown KV
on:
  pull_request:
    types: [closed]

jobs:
  teardown:
    runs-on: ubuntu-latest
    steps:
      - name: Delete ephemeral KV namespace
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          # Retrieve KV_NAMESPACE_ID stored in the environment or a prior comment
          KV_ID="${{ vars.KV_NAMESPACE_ID }}"
          curl -s -X DELETE \
            "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${KV_ID}" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.success'

          npx wrangler delete --name "pr-${{ github.event.number }}-preview" --force
```

## Anti-patterns

- **Reusing the production KV namespace in preview**: Seed data mutations bleed into production reads. Always create a dedicated namespace per PR.
- **Seeding inside the worker at startup**: Adds cold-start latency and makes seeds non-deterministic across replicas.
- **Skipping teardown**: Orphaned KV namespaces accumulate and count toward account namespace limits (currently 100 per account on free, 1000 on paid).
- **Storing binary values as raw bytes in bulk PUT**: The bulk endpoint expects UTF-8 strings; base64-encode binary values and decode in the worker.

## Gotchas

- KV has **eventual consistency** with up to 60 s propagation globally after a write. Integration tests that read immediately after seeding may see stale values on edge nodes not yet in sync. Use `cf-ray` header to pin to a single colo during tests or add a short stabilisation delay.
- The bulk PUT limit is **10 000 key-value pairs per request**; split large fixtures into batches.
- `wrangler kv:bulk put` CLI reads from a file path, not stdin — use `--path /tmp/kv-bulk.json`.
- Namespace title must be **unique per account**; prefix with `pr-{number}` to prevent collisions from concurrent PRs.
- `CF_API_TOKEN` requires the **Workers KV Storage:Edit** permission scope.

## Verification

```bash
# Check namespace was created
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '[.result[] | select(.title | startswith("pr-"))]'

# Spot-check a seeded key
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${KV_ID}/values/my-key" \
  -H "Authorization: Bearer ${CF_API_TOKEN}"
```

## Related

- `github-actions-cloudflare-d1-migration-pipeline.md`
- `github-actions-wrangler-d1-seeding-preview-environment.md`
- `github-actions-workers-preview-environments.md`
- `github-actions-environment-protection.md`

## Sources

- https://developers.cloudflare.com/kv/api/write-key-value-pairs/#write-multiple-key-value-pairs
- https://developers.cloudflare.com/api/resources/kv/subresources/namespaces/methods/create/
- https://developers.cloudflare.com/workers/wrangler/commands/#kvbulk
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/store-information-in-variables
