# Migrating wrangler.toml to wrangler.jsonc

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your `wrangler.toml` has grown large and hard to maintain: no inline comments on individual
bindings, no JSON Schema autocomplete in VS Code, and CI validation errors that are hard to
diagnose. You want to migrate to `wrangler.jsonc` to get IDE intellisense, schema-backed
linting, and readable comments next to each binding declaration.

## Context

Wrangler ≥ 3.22 (released late 2024) accepts `wrangler.jsonc` as a first-class alternative
to `wrangler.toml`. JSONC is JSON with C-style `//` and `/* */` comments, the same format
used by `tsconfig.json`. Wrangler auto-detects which format to use by filename; only one
config file should exist per project root. The JSON Schema published at
`https://json.schemastore.org/wrangler` covers both formats and is updated alongside
Wrangler releases. Migrating provides schema-validated intellisense in VS Code, JetBrains,
and any editor with JSON Schema support.

## 1. Why JSONC Over TOML

| Concern | TOML | JSONC |
|---|---|---|
| Inline comments on bindings | No | Yes |
| JSON Schema intellisense | Partial (toml-specific schema) | Full |
| Programmatic generation/patching | Requires `@iarna/toml` | `JSON.parse` / `JSON.stringify` |
| Array-of-tables syntax | `[[env.production.kv_namespaces]]` | Standard JSON array |
| Merge conflicts in git | Harder (positional blocks) | Easier (keyed objects) |

## 2. TOML to JSONC Conversion Reference

Common TOML constructs and their JSONC equivalents:

```toml
# wrangler.toml (before)
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[vars]
ENVIRONMENT = "production"
API_BASE_URL = "https://api.example.com"

[[kv_namespaces]]
binding = "CACHE"
id = "abc123"
preview_id = "xyz789"

[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id = "def456"

[env.staging]
vars = { ENVIRONMENT = "staging", API_BASE_URL = "https://staging.api.example.com" }

[[env.staging.kv_namespaces]]
binding = "CACHE"
id = "stg111"
preview_id = "stg222"
```

```jsonc
// wrangler.jsonc (after)
{
  "name": "my-worker",
  "main": "src/index.ts",
  "compatibility_date": "2024-09-23",
  "compatibility_flags": ["nodejs_compat"],

  // Static environment variables — no secrets here
  "vars": {
    "ENVIRONMENT": "production",
    "API_BASE_URL": "https://api.example.com"
  },

  "kv_namespaces": [
    {
      "binding": "CACHE",
      "id": "abc123",
      "preview_id": "xyz789" // used by wrangler dev --remote
    }
  ],

  "d1_databases": [
    {
      "binding": "DB",
      "database_name": "my-db",
      "database_id": "def456"
    }
  ],

  "env": {
    "staging": {
      "vars": {
        "ENVIRONMENT": "staging",
        "API_BASE_URL": "https://staging.api.example.com"
      },
      "kv_namespaces": [
        {
          "binding": "CACHE",
          "id": "stg111",
          "preview_id": "stg222"
        }
      ]
    }
  }
}
```

## 3. VS Code Schema Validation

Add the schema reference as the first line of `wrangler.jsonc` to activate intellisense:

```jsonc
// wrangler.jsonc
// @ts-nocheck — not a TS file; comment prevents TS server parsing errors
{
  "$schema": "https://json.schemastore.org/wrangler",
  "name": "my-worker"
  // ...
}
```

Or configure project-wide in `.vscode/settings.json`:

```jsonc
// .vscode/settings.json
{
  "json.schemas": [
    {
      "fileMatch": ["wrangler.jsonc", "wrangler.json"],
      "url": "https://json.schemastore.org/wrangler"
    }
  ]
}
```

## 4. Automating the Migration

A one-shot Node script to convert an existing `wrangler.toml`:

```typescript
// scripts/migrate-wrangler-config.ts
import { parse } from '@iarna/toml';
import { readFileSync, writeFileSync, renameSync } from 'node:fs';

const toml = readFileSync('wrangler.toml', 'utf8');
const parsed = parse(toml);

// JSONC doesn't support trailing commas in JSON.stringify output,
// but comments can be added by post-processing the string.
const jsonc = JSON.stringify(parsed, null, 2);

writeFileSync('wrangler.jsonc', jsonc, 'utf8');
// Keep wrangler.toml as a backup before removing
renameSync('wrangler.toml', 'wrangler.toml.bak');

console.log('Migrated to wrangler.jsonc — review and add comments, then delete .bak');
```

```bash
npx tsx scripts/migrate-wrangler-config.ts
# Then manually add comments and verify with:
wrangler whoami  # triggers config parse; exits 0 if valid
```

## 5. CI Validation

Lint the JSONC config in CI to catch schema violations before deploy:

```yaml
# .github/workflows/lint.yml
- name: Validate wrangler.jsonc schema
  run: |
    npx ajv-cli validate \
      --spec=draft2020 \
      -s node_modules/wrangler/config-schema.json \
      -d wrangler.jsonc \
      --strict=false
```

Or use `wrangler deploy --dry-run` which validates the config without deploying:

```bash
wrangler deploy --dry-run --outdir dist-check
```

## 6. Multi-Environment Env Override Pattern

JSONC makes environment-specific overrides more readable:

```jsonc
{
  "name": "my-worker",
  "compatibility_date": "2024-09-23",
  "r2_buckets": [
    {
      "binding": "ASSETS",
      "bucket_name": "assets-prod"
    }
  ],
  "env": {
    // Preview environment uses a separate R2 bucket to avoid polluting prod
    "preview": {
      "r2_buckets": [
        {
          "binding": "ASSETS",
          "bucket_name": "assets-preview"
        }
      ]
    }
  }
}
```

## Anti-patterns

- **Keeping both `wrangler.toml` and `wrangler.jsonc`** — Wrangler raises an error if both
  exist in the same directory. Delete (or rename) the TOML file after migration.
- **Using standard `JSON` (without comments)** — name the file `.jsonc`, not `.json`. A
  `.json` extension causes editors and schema validators to reject C-style comments.
- **Storing secrets in `vars`** — neither format is appropriate for secrets. Use
  `wrangler secret put` / `wrangler secret bulk` regardless of config format.
- **Skipping `$schema`** — without the schema reference, editors will not surface typos in
  binding keys (`kv_namepaces` instead of `kv_namespaces`) until `wrangler deploy` fails.

## Gotchas

- The `@iarna/toml` parser preserves numeric strings as numbers; check that IDs like
  `database_id` remain strings in the output JSON (they should, since TOML strings stay
  strings, but verify with `typeof parsed.d1_databases[0].database_id === 'string'`).
- JSONC comments are stripped by Wrangler's parser before validation; VS Code's JSON
  language server also handles them. Plain `JSON.parse` will throw — use
  `import { parse } from 'jsonc-parser'` in any tooling that needs to read the file
  programmatically.
- Wrangler `--config` flag accepts either format: `wrangler deploy --config wrangler.jsonc`
  works in scripts that specify the config path explicitly.

## Verification

```bash
# Confirm wrangler accepts the new file
wrangler deploy --dry-run 2>&1 | grep -E '(Error|Successfully)'

# Schema check via VS Code CLI (optional)
code --install-extension redhat.vscode-yaml
# Then open wrangler.jsonc and check Problems panel for schema errors

# Ensure TOML backup is gone once migration is confirmed
ls wrangler.toml 2>/dev/null && echo "WARNING: TOML still present" || echo "Clean"
```

## Related

- `wrangler-config-validation-ci.md`
- `wrangler-types-auto-generation-ci-pipeline.md`
- `wrangler-dev-local-d1-r2-kv.md`
- `devcontainer-cloudflare-workers-d1-r2-full.md`

## Sources

- Wrangler configuration documentation — https://developers.cloudflare.com/workers/wrangler/configuration/
- SchemaStore wrangler schema — https://json.schemastore.org/wrangler
- JSONC spec (VS Code) — https://code.visualstudio.com/docs/languages/json#_json-with-comments
- `@iarna/toml` npm — https://www.npmjs.com/package/@iarna/toml
