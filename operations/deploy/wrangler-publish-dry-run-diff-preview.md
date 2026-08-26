# Wrangler Publish Dry-Run Diff Preview

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Engineers deploying Cloudflare Workers want to preview exactly what will change—bindings, routes, environment variables, bundle size—before committing a production `wrangler deploy`. Running blind deploys causes unintended route changes and binding mismatches that are hard to roll back quickly.

## Context
Wrangler's `--dry-run` flag (combined with `--outdir`) compiles the bundle and emits a metadata JSON and script bundle to disk without publishing. By diffing the dry-run output against the currently-deployed version fetched via the Cloudflare API, CI can present a structured diff as a PR comment before any traffic is affected. This pattern slots naturally into GitHub Actions as a pre-deploy review gate.

## Generating the Dry-Run Bundle

```bash
# Produce compiled output without publishing
wrangler deploy --dry-run --outdir dist/dry-run

# Files produced:
#   dist/dry-run/<worker-name>.js        — bundled script
#   dist/dry-run/<worker-name>.js.map   — source map
#   dist/dry-run/metadata.json           — bindings, routes, compatibility_date
```

The `metadata.json` is the primary diff surface. It contains every binding definition, every route pattern, the compatibility date, and cron triggers.

## Fetching the Deployed Baseline

```typescript
// scripts/fetch-deployed-metadata.ts
import { execSync } from "node:child_process";
import fs from "node:fs";

interface WorkerMetadata {
  bindings: Array<{ type: string; name: string; [key: string]: unknown }>;
  compatibility_date: string;
  routes: Array<{ pattern: string; zone_name?: string }>;
  cron_triggers?: string[];
}

async function fetchDeployedMetadata(
  workerName: string,
  accountId: string,
  apiToken: string
): Promise<WorkerMetadata | null> {
  const url =
    `https://api.cloudflare.com/client/v4/accounts/${accountId}` +
    `/workers/scripts/${workerName}/bindings`;

  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${apiToken}` },
  });

  if (!res.ok) {
    if (res.status === 404) return null; // First deploy
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }

  const json = (await res.json()) as { result: WorkerMetadata["bindings"] };

  // Also fetch route list
  const routesRes = await fetch(
    `https://api.cloudflare.com/client/v4/zones?name=${process.env.CF_ZONE_NAME}`,
    { headers: { Authorization: `Bearer ${apiToken}` } }
  );
  const routesJson = await routesRes.json();

  return {
    bindings: json.result,
    compatibility_date: "unknown", // read from deployed script details separately
    routes: routesJson?.result ?? [],
  };
}

const deployed = await fetchDeployedMetadata(
  process.env.WORKER_NAME!,
  process.env.CF_ACCOUNT_ID!,
  process.env.CF_API_TOKEN!
);

fs.writeFileSync(
  "dist/deployed-metadata.json",
  JSON.stringify(deployed, null, 2)
);
```

## Diffing and Reporting

```typescript
// scripts/diff-metadata.ts
import fs from "node:fs";
import { diffJson } from "diff"; // npm i diff @types/diff

const incoming = JSON.parse(
  fs.readFileSync("dist/dry-run/metadata.json", "utf8")
);
const deployed = JSON.parse(
  fs.readFileSync("dist/deployed-metadata.json", "utf8")
);

const changes = diffJson(deployed, incoming);

let hasChanges = false;
let report = "## Wrangler Dry-Run Diff\n\n";
report += "```diff\n";

for (const part of changes) {
  if (part.added) {
    hasChanges = true;
    report += part.value
      .split("\n")
      .map((l) => `+ ${l}`)
      .join("\n");
  } else if (part.removed) {
    hasChanges = true;
    report += part.value
      .split("\n")
      .map((l) => `- ${l}`)
      .join("\n");
  } else {
    // Context lines — include only first/last 3
    const lines = part.value.split("\n").filter(Boolean);
    const ctx = lines.slice(0, 3);
    if (lines.length > 6) ctx.push("...");
    ctx.push(...lines.slice(-3));
    report += ctx.map((l) => `  ${l}`).join("\n");
  }
}

report += "\n```\n";

if (!hasChanges) {
  report = "## Wrangler Dry-Run Diff\n\nNo metadata changes detected.";
}

// Bundle size delta
const { size: newSize } = fs.statSync(
  `dist/dry-run/${process.env.WORKER_NAME}.js`
);
report += `\n**Bundle size**: ${(newSize / 1024).toFixed(1)} KB`;

fs.writeFileSync("dist/diff-report.md", report);
console.log(report);

// Fail CI if bindings were removed (breaking change guard)
const removedBindings = changes
  .filter((p) => p.removed)
  .some((p) => p.value.includes('"bindings"'));

if (removedBindings) {
  console.error("ERROR: binding removal detected — confirm intentional.");
  process.exit(1);
}
```

## GitHub Actions Integration

```yaml
# .github/workflows/deploy.yml
name: Deploy Workers

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  dry-run-diff:
    name: Dry-run diff preview
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - run: npm ci

      - name: Wrangler dry-run
        run: npx wrangler deploy --dry-run --outdir dist/dry-run
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Fetch deployed baseline
        run: npx tsx scripts/fetch-deployed-metadata.ts
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          WORKER_NAME: ${{ vars.WORKER_NAME }}
          CF_ZONE_NAME: ${{ vars.CF_ZONE_NAME }}

      - name: Compute diff
        run: npx tsx scripts/diff-metadata.ts
        env:
          WORKER_NAME: ${{ vars.WORKER_NAME }}

      - name: Post diff as PR comment
        if: github.event_name == 'pull_request'
        uses: marocchino/sticky-pull-request-comment@v2
        with:
          path: dist/diff-report.md
          header: wrangler-dry-run-diff

  deploy:
    name: Deploy to production
    needs: dry-run-diff
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

## Bundle Size Regression Guard

```bash
#!/usr/bin/env bash
# scripts/check-bundle-size.sh
set -euo pipefail

WORKER=${WORKER_NAME:?}
MAX_KB=${MAX_BUNDLE_KB:-1024}  # default 1 MB

SIZE_BYTES=$(stat -c%s "dist/dry-run/${WORKER}.js")
SIZE_KB=$(( SIZE_BYTES / 1024 ))

echo "Bundle size: ${SIZE_KB} KB (limit: ${MAX_KB} KB)"

if (( SIZE_KB > MAX_KB )); then
  echo "ERROR: bundle exceeds ${MAX_KB} KB limit (${SIZE_KB} KB)" >&2
  exit 1
fi
```

## Anti-patterns
- Skipping `--dry-run` entirely and relying only on post-deploy smoke tests — diff is lost.
- Comparing against a stale local copy instead of fetching the live API metadata — drift goes undetected.
- Treating binding additions as safe with no review — added bindings can expose unintended KV or R2 access.
- Running dry-run in a different environment than the actual deploy target — wrangler.toml `[env.*]` mismatch silently produces wrong metadata.
- Storing the API token needed for baseline fetch in the diff artifact — rotate and scope tokens per job.

## Gotchas
- `--dry-run` does not contact the Cloudflare API, so it cannot validate that referenced KV namespaces, R2 buckets, or D1 databases actually exist in the target account.
- The emitted `metadata.json` format is an internal Wrangler artifact and may change across minor Wrangler versions — pin `wrangler` in `package.json`.
- Routes in the dry-run output may differ from API-returned routes if the zone name resolves differently between environments.
- Source maps are emitted by default; add `--no-bundle` only if the project truly has no bundling step, otherwise the output is incorrect.
- On first deploy (no existing script), the baseline fetch returns `null`; the diff script must handle this case explicitly.

## Verification
1. Open a PR that adds a new KV binding to `wrangler.toml`.
2. Confirm the GitHub Actions `dry-run-diff` job comments a `+` diff line showing the new binding.
3. Open a PR that removes a binding; confirm CI exits non-zero and the PR is blocked.
4. Merge a no-op whitespace change; confirm the comment reads "No metadata changes detected."
5. Check `dist/diff-report.md` artifact is uploaded and readable from the Actions summary.

## Related
- `wrangler-environments-promotion-pipeline.md`
- `wrangler-config-validation-pre-deploy-ci-hook.md`
- `workers-bundle-analysis-regression-ci.md`
- `deploy-gate-antipatterns.md`

## Sources
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/api/operations/worker-script-list-bindings
- https://github.com/nicolo-ribaudo/diff
