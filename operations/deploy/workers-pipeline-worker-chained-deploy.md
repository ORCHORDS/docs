# Chained Multi-Worker Deploy Pipeline

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your architecture has multiple interdependent Workers — a shared library Worker, an API
Worker that calls it, and a BFF (Backend for Frontend) Worker that calls the API Worker.
You need a CI pipeline that:
1. Deploys the shared library Worker first.
2. Captures its version ID and pins it in the API Worker's service binding.
3. Deploys the API Worker and pins its version in the BFF Worker's service binding.
4. Deploys the BFF Worker last.

This guarantees each layer talks to an exact version of its dependency, not "latest".

## Context

- Cloudflare Workers **Service Bindings** with optional version pinning
  (`service = { name = "...", entrypoint = "...", version_id = "..." }`).
- Workers Versions API: `wrangler versions upload` + `wrangler deployments create`.
- The pipeline uses GitHub Actions with sequential jobs and `outputs` to pass version IDs
  between jobs.

---

## Section 1 — Wrangler configuration files with version-pinned bindings

```toml
# workers/lib-worker/wrangler.toml
name = "lib-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"
```

```toml
# workers/api-worker/wrangler.toml
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

# Service binding — version_id is injected by CI at deploy time
# (placeholder overridden via --var or patch script before deploy)
[[services]]
binding = "LIB"
service = "lib-worker"
# version_id = ""  <-- set dynamically; see pipeline below
```

```toml
# workers/bff-worker/wrangler.toml
name = "bff-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[services]]
binding = "API"
service = "api-worker"
# version_id = ""  <-- set dynamically
```

Because `wrangler.toml` does not natively support environment variable interpolation
inside `[[services]]`, we patch the TOML file before deploying:

```typescript
// scripts/pin-service-binding.ts
import { readFileSync, writeFileSync } from 'node:fs';

/**
 * Patch the [[services]] block in a wrangler.toml to pin a version_id
 * for the named service binding.
 */
export function pinServiceBinding(
  tomlPath: string,
  bindingName: string,
  versionId: string,
): void {
  let content = readFileSync(tomlPath, 'utf8');

  // Find the [[services]] block that has `binding = "<bindingName>"`
  // and inject or replace the version_id line immediately after the service line.
  const bindingBlockRegex = new RegExp(
    `(\\[\\[services\\]\\][^]*?binding\\s*=\\s*"${bindingName}"[^]*?)` +
    `(service\\s*=\\s*"[^"]+")`,
    'm',
  );

  if (!bindingBlockRegex.test(content)) {
    throw new Error(`Could not find [[services]] block for binding "${bindingName}" in ${tomlPath}`);
  }

  // Remove any existing version_id in this block first
  content = content.replace(
    new RegExp(`(binding\\s*=\\s*"${bindingName}"[^\\[]*?)version_id\\s*=\\s*"[^"]*"`, 's'),
    '$1',
  );

  // Append version_id after the service = line in this block
  content = content.replace(
    new RegExp(`(binding\\s*=\\s*"${bindingName}"([^\\[]*?)service\\s*=\\s*"([^"]+)")`, 's'),
    `$1\nversion_id = "${versionId}"`,
  );

  writeFileSync(tomlPath, content, 'utf8');
  console.log(`Pinned ${bindingName} → ${versionId} in ${tomlPath}`);
}

// CLI: npx tsx scripts/pin-service-binding.ts <toml> <binding> <version_id>
const [,, tomlPath, bindingName, versionId] = process.argv;
if (tomlPath && bindingName && versionId) {
  pinServiceBinding(tomlPath, bindingName, versionId);
}
```

---

## Section 2 — Chained GitHub Actions pipeline

```yaml
# .github/workflows/chained-deploy.yml
name: Chained Worker Deploy

on:
  push:
    branches: [main]

env:
  CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
  CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

jobs:
  # ── 1. Lib Worker ────────────────────────────────────────────────────────────
  deploy-lib:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: workers/lib-worker
    outputs:
      version_id: ${{ steps.upload.outputs.version_id }}

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
      - run: npm run build

      - name: Upload lib-worker version
        id: upload
        run: |
          OUTPUT=$(npx wrangler versions upload --message "lib-worker@${{ github.sha }}" 2>&1)
          echo "$OUTPUT"
          VERSION_ID=$(echo "$OUTPUT" | grep -oP '(?<=Version ID: )[\w-]+' | head -1)
          echo "version_id=${VERSION_ID}" >> "$GITHUB_OUTPUT"

      - name: Route 100% traffic to new lib-worker version
        run: |
          npx wrangler deployments create \
            --version-id "${{ steps.upload.outputs.version_id }}" \
            --version-percentage 100 \
            --message "chained-deploy lib-worker"

  # ── 2. API Worker ────────────────────────────────────────────────────────────
  deploy-api:
    needs: deploy-lib
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: workers/api-worker
    outputs:
      version_id: ${{ steps.upload.outputs.version_id }}

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
      - run: npm run build

      - name: Pin lib-worker version in api-worker wrangler.toml
        run: |
          npx tsx ../../scripts/pin-service-binding.ts \
            wrangler.toml LIB "${{ needs.deploy-lib.outputs.version_id }}"

      - name: Upload api-worker version
        id: upload
        run: |
          OUTPUT=$(npx wrangler versions upload --message "api-worker@${{ github.sha }}" 2>&1)
          echo "$OUTPUT"
          VERSION_ID=$(echo "$OUTPUT" | grep -oP '(?<=Version ID: )[\w-]+' | head -1)
          echo "version_id=${VERSION_ID}" >> "$GITHUB_OUTPUT"

      - name: Route 100% traffic to new api-worker version
        run: |
          npx wrangler deployments create \
            --version-id "${{ steps.upload.outputs.version_id }}" \
            --version-percentage 100 \
            --message "chained-deploy api-worker"

  # ── 3. BFF Worker ────────────────────────────────────────────────────────────
  deploy-bff:
    needs: [deploy-lib, deploy-api]
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: workers/bff-worker

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
      - run: npm run build

      - name: Pin api-worker version in bff-worker wrangler.toml
        run: |
          npx tsx ../../scripts/pin-service-binding.ts \
            wrangler.toml API "${{ needs.deploy-api.outputs.version_id }}"

      - name: Upload bff-worker version
        id: upload
        run: |
          OUTPUT=$(npx wrangler versions upload --message "bff-worker@${{ github.sha }}" 2>&1)
          echo "$OUTPUT"
          VERSION_ID=$(echo "$OUTPUT" | grep -oP '(?<=Version ID: )[\w-]+' | head -1)
          echo "version_id=${VERSION_ID}" >> "$GITHUB_OUTPUT"

      - name: Route 100% traffic to new bff-worker version
        run: |
          npx wrangler deployments create \
            --version-id "${{ steps.upload.outputs.version_id }}" \
            --version-percentage 100 \
            --message "chained-deploy bff-worker"
```

---

## Section 3 — Verification

```bash
# Confirm each worker is bound to the expected version
npx wrangler versions list --name lib-worker
npx wrangler versions list --name api-worker
npx wrangler versions list --name bff-worker

# Verify service binding on the API worker
npx wrangler versions view <api-worker-version-id>
# Look for: services: [{binding: "LIB", service: "lib-worker", version_id: "..."}]

# End-to-end smoke test: call the BFF and assert it returns a valid response
curl -fsSL https://bff-worker.<account>.workers.dev/health | jq '.'

# Check that no worker is routing to the old version
npx wrangler deployments list --name lib-worker
# Expected: only the latest deployment at 100%
```

---

## Anti-patterns

- **Using `wrangler deploy` instead of `versions upload` + `deployments create`** —
  `wrangler deploy` always routes 100 % to the new version immediately and does not
  preserve a version ID you can pass as a service binding pin.
- **Deploying all workers in parallel** — if the BFF deploys before the API Worker, the
  old API version may still be live; always deploy dependency → dependent in order.
- **Editing `wrangler.toml` with `sed` or inline `echo`** — fragile against TOML
  formatting changes; use the typed patcher script.
- **Not pinning the service binding version** — without version pinning, a service
  binding resolves to "latest deployment", which can change between the time the binding
  is evaluated and when the request is served during a rolling deploy.

## Gotchas

- Version ID pinning in service bindings is a Workers Versions API feature — it requires
  the Paid plan and wrangler ≥ 3.40.0.
- `wrangler versions upload` does NOT trigger the `[build]` command; always run your
  build step before uploading.
- The TOML patcher modifies the working copy of `wrangler.toml` inside the runner; this
  does not affect the git repository because the commit is read-only (`actions/checkout@v4`
  checks out at the commit SHA, and pushes from CI are blocked by branch protection).
- If a deploy-lib job fails mid-pipeline, deploy-api is blocked by `needs: deploy-lib`
  so the partial state is safe — lib-worker stays at the previous version.

## Related

- `workers-version-binding-traffic-migration.md`
- `workers-deployment-gates-manual-approval.md`
- `workers-deployment-slack-webhook-notification.md`

## Sources

- Workers Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Workers Versions API: https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- Wrangler versions commands: https://developers.cloudflare.com/workers/wrangler/commands/#versions
