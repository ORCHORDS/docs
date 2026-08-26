# Wrangler Config Validation in CI

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

`wrangler deploy` fails in CI with cryptic binding or compatibility-date errors that
only surface at deploy time. The local developer never sees them because `wrangler dev`
is tolerant of missing fields. You want to catch invalid `wrangler.toml` configurations
at the earliest possible CI stage — before running tests or attempting a deploy.

## Context

Wrangler exposes a `wrangler deploy --dry-run` flag that validates the full config
and emits the bundled output without actually uploading anything. Pairing this with
`tsc --noEmit` and a custom TOML schema check lets you build a cheap, fast "config
gate" that runs in seconds and blocks merges before they burn deploy credits.

Supported Wrangler version: ≥ 3.60. Cloudflare Workers runtime, TypeScript project
managed by pnpm workspaces.

---

## 1. Dry-run validation step

```typescript
// scripts/validate-wrangler-config.ts
import { execSync } from "node:child_process";
import { existsSync } from "node:fs";

const CONFIG_FILES = ["wrangler.toml", "wrangler.jsonc"];

for (const cfg of CONFIG_FILES) {
  if (!existsSync(cfg)) continue;

  try {
    execSync(`wrangler deploy --dry-run --config ${cfg} --outdir /tmp/dry-run-out`, {
      stdio: "inherit",
      env: {
        ...process.env,
        // Provide a dummy token so Wrangler can evaluate binding references
        CLOUDFLARE_API_TOKEN: process.env.CLOUDFLARE_API_TOKEN ?? "dummy-token-for-dry-run",
      },
    });
    console.log(`✓ ${cfg} is valid`);
  } catch {
    console.error(`✗ ${cfg} failed dry-run validation`);
    process.exit(1);
  }
}
```

## 2. TOML schema validation with `@ltd/j-toml` + ajv

```typescript
// scripts/schema-check-wrangler.ts
import { readFileSync } from "node:fs";
import { parse } from "@ltd/j-toml";
import Ajv from "ajv";

// Minimal schema enforcing fields required by Cloudflare Workers
const SCHEMA = {
  type: "object",
  required: ["name", "main", "compatibility_date"],
  properties: {
    name: { type: "string", minLength: 1 },
    main: { type: "string" },
    compatibility_date: {
      type: "string",
      pattern: "^\\d{4}-\\d{2}-\\d{2}$",
    },
    compatibility_flags: {
      type: "array",
      items: { type: "string" },
    },
    kv_namespaces: {
      type: "array",
      items: {
        type: "object",
        required: ["binding", "id"],
        properties: {
          binding: { type: "string" },
          id: { type: "string" },
          preview_id: { type: "string" },
        },
      },
    },
    d1_databases: {
      type: "array",
      items: {
        type: "object",
        required: ["binding", "database_name", "database_id"],
      },
    },
  },
} as const;

const raw = readFileSync("wrangler.toml", "utf8");
const config = parse(raw, { bigint: false });

const ajv = new Ajv({ allErrors: true });
const valid = ajv.validate(SCHEMA, config);

if (!valid) {
  console.error("wrangler.toml schema errors:");
  for (const err of ajv.errors ?? []) {
    console.error(`  ${err.instancePath || "/"} — ${err.message}`);
  }
  process.exit(1);
}

console.log("wrangler.toml schema OK");
```

## 3. CI workflow — GitHub Actions

```yaml
# .github/workflows/wrangler-validate.yml
name: Wrangler Config Validation

on:
  pull_request:
    paths:
      - "wrangler.toml"
      - "wrangler.jsonc"
      - "src/**"

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: TypeScript type-check
        run: pnpm tsc --noEmit

      - name: Schema-validate wrangler.toml
        run: pnpm tsx scripts/schema-check-wrangler.ts

      - name: Wrangler dry-run
        run: pnpm wrangler deploy --dry-run --outdir /tmp/dry-run
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

## 4. Compatibility-date drift detection

```typescript
// scripts/check-compat-date.ts
import { readFileSync } from "node:fs";
import { parse } from "@ltd/j-toml";

const WARN_AFTER_DAYS = 90;

const { compatibility_date } = parse(readFileSync("wrangler.toml", "utf8"), {
  bigint: false,
}) as { compatibility_date: string };

const configDate = new Date(compatibility_date);
const ageMs = Date.now() - configDate.getTime();
const ageDays = Math.floor(ageMs / (1000 * 60 * 60 * 24));

if (ageDays > WARN_AFTER_DAYS) {
  const latest = new Date().toISOString().slice(0, 10);
  console.warn(
    `⚠ compatibility_date is ${ageDays} days old (${compatibility_date}). ` +
      `Consider updating to ${latest}.`
  );
  // Exit 0 — warning only, not a hard failure
}
```

## 5. Pre-commit hook integration

```bash
# .husky/pre-commit
#!/usr/bin/env sh
. "$(dirname "$0")/_/husky.sh"

# Fast path: skip if wrangler.toml unchanged
if git diff --cached --name-only | grep -qE "wrangler\.(toml|jsonc)"; then
  pnpm tsx scripts/schema-check-wrangler.ts
fi
```

## Anti-patterns

- Running `wrangler deploy` (no `--dry-run`) in CI validation steps — this consumes
  deploy quota and may push broken code to production preview environments.
- Skipping schema validation because "wrangler will catch it" — Wrangler error messages
  at deploy time are harder to act on than structured AJV output in a PR check.
- Hardcoding `CLOUDFLARE_API_TOKEN=x` in committed scripts — use CI secrets and provide
  a dummy value only when the token is genuinely not needed (dry-run only validates
  bundle shape, not live binding resolution).

## Gotchas

- `--dry-run` does NOT validate that KV namespace IDs or D1 database IDs actually exist
  in your Cloudflare account. Schema checks cover shape; live binding checks require a
  deploy or the `wrangler kv:namespace list` / `wrangler d1 list` approach.
- `wrangler.jsonc` parsing in schema scripts requires a JSONC-aware parser (e.g.
  `comment-json`) — standard `JSON.parse` will throw on comments.
- The `--outdir` flag is required with `--dry-run` since Wrangler 3.40; omitting it
  causes a misleading "no output directory" error.

## Verification

```bash
# Should print "wrangler.toml schema OK" and exit 0
pnpm tsx scripts/schema-check-wrangler.ts

# Should bundle without uploading and print "Total Upload: XX KiB"
pnpm wrangler deploy --dry-run --outdir /tmp/dry-out
```

## Related

- `wrangler-types-auto-generation-ci-pipeline.md`
- `typescript-cloudflare-workers-strict.md`
- `biome-linter-formatter-cloudflare-workers.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
- https://ajv.js.org/
