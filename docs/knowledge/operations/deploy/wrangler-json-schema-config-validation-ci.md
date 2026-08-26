# Wrangler Config JSON Schema Validation CI Gate

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A pull request introduces a typo in `wrangler.toml` — a misspelled binding name,
an invalid compatibility date format, or an unrecognised field. The error is only
discovered when the deploy job runs `wrangler deploy`, which fails with a
cryptic message like `Unknown field "kv_namespace"` (missing the `s`) at the end
of an otherwise long CI run.

A second variant: the example project monorepo has 12 Workers packages, each with its own
`wrangler.toml`. A structural error in one file (e.g., a missing `name` field after
a copy-paste) passes lint and TypeScript checks but breaks production deploys.

Goal: add a fast, cheap CI gate that validates every `wrangler.toml` and
`wrangler.json` against a JSON Schema before any deployment step runs.

## Context

Wrangler 3.x ships with a TypeScript-first internal validation layer but does not
expose a standalone `wrangler validate` CLI command. The Community Edition of the
Wrangler Config JSON Schema (maintained at
`cloudflare/workers-types/wrangler-schema.json`) can be used with any JSON Schema
v7 validator such as `ajv` or `@cfworkers/schema-cli`.

`wrangler.toml` must be transpiled to JSON before schema validation. The
`@iarna/toml` package is the recommended parser as it produces output compatible
with the Wrangler config shape.

---

## Section 1 — Schema Validation Script (TypeScript / AJV)

```typescript
// scripts/validate-wrangler-configs.ts
import { glob } from 'glob';
import { parse as parseTOML } from '@iarna/toml';
import Ajv, { type ValidateFunction } from 'ajv';
import addFormats from 'ajv-formats';
import fs from 'fs';
import path from 'path';

// Download schema once with: curl -o scripts/wrangler-schema.json
//   https://raw.githubusercontent.com/cloudflare/workers-sdk/main/packages/wrangler/config-schema.json
const SCHEMA_PATH = path.join(__dirname, 'wrangler-schema.json');

function buildValidator(): ValidateFunction {
  const ajv = new Ajv({
    strict: false,         // Wrangler schema uses $comment; strict mode rejects it
    allErrors: true,
    verbose: true,
  });
  addFormats(ajv);         // required for "date" format on compatibility_date

  const schema = JSON.parse(fs.readFileSync(SCHEMA_PATH, 'utf8'));
  return ajv.compile(schema);
}

function loadConfig(filePath: string): Record<string, unknown> {
  const raw = fs.readFileSync(filePath, 'utf8');
  if (filePath.endsWith('.json')) {
    return JSON.parse(raw);
  }
  // TOML → plain JS object
  return parseTOML(raw) as Record<string, unknown>;
}

async function main(): Promise<void> {
  const validate = buildValidator();
  const pattern = process.argv[2] ?? '**/wrangler.{toml,json}';
  const ignorePatterns = ['**/node_modules/**', '**/.wrangler/**'];

  const files = await glob(pattern, { ignore: ignorePatterns });

  if (files.length === 0) {
    console.warn('No wrangler config files found.');
    return;
  }

  let allPassed = true;

  for (const file of files.sort()) {
    let config: Record<string, unknown>;
    try {
      config = loadConfig(file);
    } catch (err) {
      console.error(`[PARSE ERROR] ${file}: ${(err as Error).message}`);
      allPassed = false;
      continue;
    }

    const valid = validate(config);
    if (!valid && validate.errors) {
      console.error(`[INVALID] ${file}`);
      for (const error of validate.errors) {
        const location = error.instancePath || '(root)';
        console.error(`  ${location}: ${error.message}`);
        if (error.params && Object.keys(error.params).length > 0) {
          console.error(`    params: ${JSON.stringify(error.params)}`);
        }
      }
      allPassed = false;
    } else {
      console.log(`[OK]      ${file}`);
    }
  }

  if (!allPassed) {
    console.error('\nSchema validation failed. Fix the errors above before deploying.');
    process.exit(1);
  }

  console.log(`\nAll ${files.length} config file(s) passed schema validation.`);
}

main().catch((err) => { console.error(err); process.exit(1); });
```

## Section 2 — Schema Download and Cache

```bash
#!/usr/bin/env bash
# scripts/fetch-wrangler-schema.sh
# Run once to pin the schema; commit the file to the repo for reproducibility.
set -euo pipefail

SCHEMA_URL="https://raw.githubusercontent.com/cloudflare/workers-sdk/main/packages/wrangler/config-schema.json"
OUT="scripts/wrangler-schema.json"

curl -fsSL "$SCHEMA_URL" -o "$OUT"
echo "Schema downloaded → $OUT"
echo "Schema version: $(jq -r '."$schema"' "$OUT")"

# Pin to a specific workers-sdk tag to avoid schema drift:
# TAGGED_URL="https://raw.githubusercontent.com/cloudflare/workers-sdk/wrangler@3.x.y/packages/wrangler/config-schema.json"
```

```jsonc
// .github/dependabot.yml — keep the pinned schema fresh
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
  # Note: wrangler-schema.json is manually refreshed quarterly via the
  # fetch-wrangler-schema.sh script — no automated dependabot support for
  # raw JSON schema files. Add a quarterly reminder Routine.
```

## Section 3 — GitHub Actions CI Gate

```yaml
# .github/workflows/wrangler-config-validation.yml
name: Validate Wrangler Configs

on:
  pull_request:
    paths:
      - '**/wrangler.toml'
      - '**/wrangler.json'
      - 'scripts/wrangler-schema.json'

  push:
    branches: [main, staging]

jobs:
  validate:
    name: JSON Schema validation
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Validate all wrangler configs
        run: npx ts-node scripts/validate-wrangler-configs.ts '**/wrangler.{toml,json}'

      - name: Check for unregistered wrangler configs
        # Ensures new Workers packages are added to the known list
        run: |
          FOUND=$(find . -name "wrangler.toml" -o -name "wrangler.json" \
            | grep -v node_modules | grep -v .wrangler | sort)
          KNOWN=$(cat .known-wrangler-configs | sort)
          DIFF=$(diff <(echo "$KNOWN") <(echo "$FOUND") || true)
          if [ -n "$DIFF" ]; then
            echo "Unregistered wrangler config files detected:"
            echo "$DIFF"
            echo "Update .known-wrangler-configs to include new Workers packages."
            exit 1
          fi
```

```text
# .known-wrangler-configs (committed to repo)
./apps/api/wrangler.toml
./apps/frontend/wrangler.toml
./workers/billing/wrangler.toml
./workers/cron/wrangler.toml
./workers/email/wrangler.toml
./workers/metrics/wrangler.toml
```

## Section 4 — Monorepo Validation with Turbo

```json
// turbo.json — add validate task
{
  "tasks": {
    "validate:wrangler": {
      "inputs": ["wrangler.toml", "wrangler.json"],
      "outputs": [],
      "cache": true
    },
    "deploy": {
      "dependsOn": ["validate:wrangler", "^deploy"]
    }
  }
}
```

```json
// apps/api/package.json
{
  "scripts": {
    "validate:wrangler": "ts-node ../../scripts/validate-wrangler-configs.ts ./wrangler.toml"
  }
}
```

## Section 5 — Custom Schema Extensions for example project Conventions

Extend the Cloudflare schema with organisation-specific rules using AJV custom
keywords.

```typescript
// scripts/validate-wrangler-configs.ts (extended section)
import Ajv from 'ajv';

function addWaspConventions(ajv: Ajv): void {
  // Rule: every wrangler.toml must have a compatibility_date >= 2025-01-01
  ajv.addKeyword({
    keyword: 'waspMinCompatDate',
    type: 'string',
    validate: (_schema: unknown, data: string) => {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(data)) return false;
      return data >= '2025-01-01';
    },
    errors: false,
  });

  // Rule: Worker names must match the example project- prefix convention
  ajv.addKeyword({
    keyword: 'waspNamePattern',
    type: 'string',
    validate: (_schema: unknown, data: string) => /^example project-[a-z0-9-]+$/.test(data),
    errors: false,
  });
}

// Patch the schema before compiling:
function patchSchema(schema: Record<string, unknown>): Record<string, unknown> {
  const patched = JSON.parse(JSON.stringify(schema)) as Record<string, unknown>;
  const props = (patched.properties as Record<string, unknown>) ?? {};

  // Enforce example project- prefix on name field
  if (props.name) {
    (props.name as Record<string, unknown>).waspNamePattern = true;
  }

  // Enforce minimum compatibility_date
  if (props.compatibility_date) {
    (props.compatibility_date as Record<string, unknown>).waspMinCompatDate = true;
  }

  return patched;
}
```

## Section 6 — Pre-commit Hook via Husky

```json
// package.json (root)
{
  "scripts": {
    "validate:wrangler": "ts-node scripts/validate-wrangler-configs.ts"
  },
  "lint-staged": {
    "**/wrangler.{toml,json}": ["ts-node scripts/validate-wrangler-configs.ts"]
  }
}
```

```bash
# .husky/pre-commit
#!/usr/bin/env sh
. "$(dirname "$0")/_/husky.sh"
npx lint-staged
```

## Anti-patterns

- **Running `wrangler deploy --dry-run` as the schema gate** — dry-run hits the
  Cloudflare API, requires credentials, and is much slower than local schema
  validation. Use schema validation first; reserve dry-run for final pre-deploy
  checks.
- **Vendoring the schema without a refresh cadence** — Wrangler adds new fields
  (e.g., `[[assets]]`, `[[pipelines]]`) frequently. A schema older than 3 months
  will miss new valid fields and produce false positives.
- **Using `strict: true` in AJV** — the Wrangler JSON Schema uses `$comment` and
  other draft-07 meta-fields that AJV strict mode rejects. Always pass
  `strict: false`.
- **Only validating changed files in a PR** — a rename or environment variable
  change in one file can affect downstream Workers packages that reference the
  same binding names. Validate all configs on every PR, using Turbo's caching to
  make it fast.

## Gotchas

- `wrangler.toml` uses TOML's array-of-tables syntax (`[[kv_namespaces]]`) which
  maps to JSON arrays. The `@iarna/toml` parser handles this correctly; `toml`
  (the older package) does not.
- The Wrangler config schema is in JSON Schema draft-07. Some AJV v8 defaults
  assume draft-2020-12. Pass `{ draft7Meta: true }` or use
  `ajv.addMetaSchema(require('ajv/dist/refs/json-schema-draft-07.json'))`.
- Environment-specific overrides in `[env.production]` are not validated against
  the full top-level schema by default — they are partial objects. The schema
  uses `additionalProperties: false` sparingly to accommodate this.
- The `name` field in `[env.production]` overrides the top-level `name`. If the
  convention rule requires the `example project-` prefix, ensure it applies to environment-
  level names too by patching the `env` definition in the schema.
- Schema validation catches structural errors but not semantic errors — e.g., a KV
  `binding` name that conflicts with a D1 `binding` name of the same identifier.
  Add a separate uniqueness check for binding names.

## Verification

```bash
# Run validation locally across all packages
npx ts-node scripts/validate-wrangler-configs.ts '**/wrangler.{toml,json}'

# Introduce a deliberate error and confirm detection
echo 'name = 123' >> apps/api/wrangler.toml  # name must be string
npx ts-node scripts/validate-wrangler-configs.ts apps/api/wrangler.toml
# Expected: [INVALID] apps/api/wrangler.toml
#   /name: must be string
git checkout apps/api/wrangler.toml   # restore

# Confirm the CI job is required for PR merges
gh pr view <number> --json statusCheckRollup \
  | jq '.statusCheckRollup[] | select(.name == "validate / JSON Schema validation")'
```

## Related

- `wrangler-config-validation-pre-deploy-ci-hook.md`
- `wrangler-ci-deploy-dry-run-validation-gate.md`
- `deploy-artifact-build-parity-ci-gate.md`
- `wrangler-environments-promotion-pipeline.md`
- `monorepo-deploy-pipeline-turborepo.md`

## Sources

- Cloudflare workers-sdk config schema source: https://github.com/cloudflare/workers-sdk/tree/main/packages/wrangler
- AJV documentation: https://ajv.js.org/
- @iarna/toml parser: https://github.com/iarna/iarna-toml
- JSON Schema draft-07: https://json-schema.org/specification-links#draft-7
- Wrangler configuration reference: https://developers.cloudflare.com/workers/wrangler/configuration/
