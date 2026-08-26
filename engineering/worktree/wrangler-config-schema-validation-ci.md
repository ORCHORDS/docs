# Wrangler Config Schema Validation in CI

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A wrangler.toml typo or stale binding reference only surfaces at deploy time, blocking the entire release pipeline.
Catching schema drift in CI—before the deploy step—prevents silent misconfigurations from reaching production.

## Context
Wrangler reads `wrangler.toml` (or `wrangler.json`) for every `wrangler deploy`, `wrangler dev`, and `wrangler tail` invocation.
The config file controls bindings (KV, D1, R2, Durable Objects, Service Bindings), compatibility dates, and environment overrides.
Wrangler 3.x ships a `--dry-run` flag and exposes its internal JSON Schema; both can be leveraged in a dedicated CI validation job that runs on every PR, independently of deployment credentials.

---

## Setup — Extract the Wrangler JSON Schema

Wrangler bundles its config schema as part of the package.  Export it once and commit it so validators can run without network access:

```bash
# Run once; commit schema.json alongside wrangler.toml
node -e "
  const s = require('@cloudflare/workers-types/experimental');
  // Wrangler 3.x publishes the schema separately:
" 2>/dev/null || \
  npx wrangler@latest config schema > .wrangler/config-schema.json
```

For monorepos, generate per-package:

```bash
#!/usr/bin/env bash
# scripts/export-wrangler-schema.sh
set -euo pipefail
SCHEMA_VERSION=$(npx wrangler --version | grep -oP '\d+\.\d+\.\d+')
echo "Exporting schema for wrangler $SCHEMA_VERSION"
npx wrangler config schema --output .wrangler/config-schema.json
```

---

## Section 1 — Validate with `wrangler deploy --dry-run`

The fastest gate: `--dry-run` parses and resolves the config without contacting the Cloudflare API, requiring no `CLOUDFLARE_API_TOKEN`.

```yaml
# .github/workflows/validate-wrangler-config.yml
name: Validate wrangler.toml

on:
  pull_request:
    paths:
      - '**/wrangler.toml'
      - '**/wrangler.json'
      - '**/wrangler.jsonc'

jobs:
  validate:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        worker:
          - packages/api-worker
          - packages/auth-worker
          - packages/queue-consumer
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      - name: Dry-run deploy (${{ matrix.worker }})
        working-directory: ${{ matrix.worker }}
        # No API token needed; --dry-run only validates config + bundle
        run: npx wrangler deploy --dry-run --outdir /tmp/wrangler-out

      - name: Assert output bundle exists
        run: test -f /tmp/wrangler-out/index.js
```

---

## Section 2 — JSON Schema Lint with `ajv-cli`

For stricter field-level validation (e.g. reject unknown keys, enforce `compatibility_date` format), pair the Wrangler schema with `ajv-cli`:

```bash
pnpm add -D ajv-cli ajv-formats
```

```typescript
// scripts/validate-wrangler-config.ts
import { execSync } from 'node:child_process';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

const SCHEMA = resolve('.wrangler/config-schema.json');

function findWranglerConfigs(root: string): string[] {
  const results: string[] = [];
  for (const entry of readdirSync(root, { withFileTypes: true, recursive: true })) {
    if (!entry.isFile()) continue;
    if (/^wrangler\.(toml|json|jsonc)$/.test(entry.name)) {
      results.push(resolve(root, entry.parentPath ?? entry.path, entry.name));
    }
  }
  return results;
}

const configs = findWranglerConfigs('packages');
let failed = false;

for (const config of configs) {
  try {
    execSync(
      `npx ajv validate -s ${SCHEMA} -d ${config} --strict=false --all-errors`,
      { stdio: 'pipe' }
    );
    console.log(`✓ ${config}`);
  } catch (err) {
    console.error(`✗ ${config}`);
    console.error((err as { stderr: Buffer }).stderr.toString());
    failed = true;
  }
}

if (failed) process.exit(1);
```

```json
// package.json (root)
{
  "scripts": {
    "validate:wrangler": "tsx scripts/validate-wrangler-config.ts"
  }
}
```

---

## Section 3 — Enforce Compatibility Date Freshness

Stale `compatibility_date` silently keeps workers on old runtime behaviour.
Assert the date is never more than 365 days behind:

```typescript
// scripts/check-compatibility-date.ts
import { readFileSync, readdirSync } from 'node:fs';
import { parse as parseTOML } from 'smol-toml';

const MAX_AGE_DAYS = 365;
const today = new Date();

function checkFile(path: string) {
  const raw = readFileSync(path, 'utf8');
  const config = parseTOML(raw) as { compatibility_date?: string };
  if (!config.compatibility_date) {
    console.error(`MISSING compatibility_date in ${path}`);
    return false;
  }
  const date = new Date(config.compatibility_date);
  const ageDays = (today.getTime() - date.getTime()) / 86_400_000;
  if (ageDays > MAX_AGE_DAYS) {
    console.error(
      `STALE compatibility_date ${config.compatibility_date} in ${path} (${Math.floor(ageDays)} days old)`
    );
    return false;
  }
  console.log(`OK  ${path}  (${Math.floor(ageDays)} days old)`);
  return true;
}

const files = readdirSync('packages', { recursive: true, withFileTypes: true })
  .filter(e => e.isFile() && e.name === 'wrangler.toml')
  .map(e => `${e.parentPath ?? e.path}/${e.name}`);

const allOk = files.map(checkFile).every(Boolean);
if (!allOk) process.exit(1);
```

---

## Anti-patterns

- Running `wrangler deploy` in CI without `--dry-run` just to validate config — wastes deploy quota and requires production credentials in PRs
- Storing the JSON Schema in-repo but never updating it — pins validation to a stale schema as Wrangler evolves
- Validating only the root `wrangler.toml` in a monorepo — environment-specific overrides in subdirectories can still drift
- Using `wrangler dev` as a proxy for config validation — it starts a local server and has different resolution semantics

## Gotchas

- `--dry-run` does NOT verify that referenced KV namespaces or D1 databases actually exist in your account; it only checks that the config is structurally valid
- `wrangler.jsonc` files require JSONC-aware parsers; `ajv-cli` processes JSON only — strip comments first with `strip-json-comments`
- The Wrangler JSON Schema path changed between Wrangler 2.x and 3.x; always use the version bundled with your pinned Wrangler
- `compatibility_flags` entries are validated as strings — an unknown flag silently passes schema validation but may error at runtime

## Verification

```bash
# Confirm dry-run works without API token
CLOUDFLARE_API_TOKEN="" npx wrangler deploy --dry-run 2>&1 | grep -E "Total Upload|Error"

# Check schema version matches installed Wrangler
node -e "const p = require('./node_modules/wrangler/package.json'); console.log(p.version)"

# Run the freshness check locally
npx tsx scripts/check-compatibility-date.ts
```

## Related

- `wrangler-environments-staging-production.md`
- `wrangler-config-inheritance-environments-workers.md`
- `github-actions-wrangler-deploy-pipeline.md`
- `wrangler-secrets-bulk-management-ci.md`
- `monorepo-wrangler-selective-deploy.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/configuration/
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://github.com/cloudflare/workers-sdk/tree/main/packages/wrangler
- https://ajv.js.org/packages/ajv-cli.html
- https://github.com/nicolo-ribaudo/smol-toml
