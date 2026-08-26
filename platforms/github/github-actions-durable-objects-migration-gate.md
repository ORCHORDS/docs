# Durable Objects Class Migration Gate in GitHub Actions

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Renaming or deleting a Durable Objects class without a migration entry in `wrangler.toml` causes Cloudflare to reject the deployment with a cryptic `Missing migration` error; you need a CI gate that detects breaking class changes before they reach production.

## Context
Durable Objects migrations must be declared explicitly in `wrangler.toml` under `[[migrations]]`. Because Wrangler validates migrations only at deploy time, teams discover the error only after merging. A pre-deploy validation job that parses `wrangler.toml`, diffs DO class declarations against the previous release tag, and blocks the PR on mismatches eliminates that late-stage failure.

## Parsing the Migration Table

A TypeScript helper reads both the current and previous `wrangler.toml` and extracts all Durable Object class names.

```typescript
// scripts/check-do-migrations.ts
import { readFileSync } from 'node:fs';
import { execSync } from 'node:child_process';
import TOML from '@iarna/toml';

interface WranglerConfig {
  durable_objects?: { bindings?: Array<{ class_name: string }> };
  migrations?: Array<{ tag: string; new_classes?: string[]; renamed_classes?: Array<{ from: string; to: string }>; deleted_classes?: string[] }>;
}

function extractClasses(config: WranglerConfig): Set<string> {
  return new Set(
    (config.durable_objects?.bindings ?? []).map((b) => b.class_name),
  );
}

const current = TOML.parse(readFileSync('wrangler.toml', 'utf8')) as WranglerConfig;
const previousRaw = execSync('git show HEAD~1:wrangler.toml', { encoding: 'utf8' });
const previous = TOML.parse(previousRaw) as WranglerConfig;

const currentClasses = extractClasses(current);
const previousClasses = extractClasses(previous);

const removed = [...previousClasses].filter((c) => !currentClasses.has(c));
const added = [...currentClasses].filter((c) => !previousClasses.has(c));

const migratedNew = new Set(
  (current.migrations ?? []).flatMap((m) => m.new_classes ?? []),
);
const migratedDeleted = new Set(
  (current.migrations ?? []).flatMap((m) => m.deleted_classes ?? []),
);
const migratedRenamed = new Set(
  (current.migrations ?? []).flatMap((m) =>
    (m.renamed_classes ?? []).map((r) => r.from),
  ),
);

const errors: string[] = [];
for (const cls of added) {
  if (!migratedNew.has(cls)) {
    errors.push(`New DO class '${cls}' not declared in [[migrations]] new_classes`);
  }
}
for (const cls of removed) {
  if (!migratedDeleted.has(cls) && !migratedRenamed.has(cls)) {
    errors.push(`Removed DO class '${cls}' not declared in [[migrations]] deleted_classes or renamed_classes`);
  }
}

if (errors.length > 0) {
  console.error('Durable Objects migration validation failed:');
  errors.forEach((e) => console.error(`  • ${e}`));
  process.exit(1);
}

console.log('DO migration check passed — all class changes are declared.');
```

## CI Workflow

```yaml
# .github/workflows/do-migration-gate.yml
name: Durable Objects Migration Gate

on:
  pull_request:
    paths:
      - 'wrangler.toml'
      - 'src/**/*.ts'

permissions:
  contents: read
  pull-requests: write

jobs:
  validate-migrations:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2        # need HEAD~1 for diff

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      - name: Run DO migration gate
        id: gate
        run: pnpm tsx scripts/check-do-migrations.ts

      - name: Post failure summary to PR
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            await github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: [
                '## ❌ Durable Objects Migration Gate Failed',
                '',
                'One or more Durable Objects class additions, removals, or renames are missing',
                'a corresponding entry in `[[migrations]]` inside `wrangler.toml`.',
                '',
                'Add the appropriate migration tag before this PR can be merged.',
              ].join('\n'),
            });
```

## Valid Migration Examples in wrangler.toml

```toml
[[migrations]]
tag = "v2"
new_classes = ["SessionStore"]

[[migrations]]
tag = "v3"
renamed_classes = [{ from = "SessionStore", to = "UserSession" }]

[[migrations]]
tag = "v4"
deleted_classes = ["LegacyCounter"]
new_classes = ["ReliableCounter"]
```

## Checking Class Renames in TypeScript

When a class is renamed, both the old binding entry is removed and the new one is added. The script must cross-reference `renamed_classes[].from` against removed names to avoid a false positive.

```typescript
// Extend the rename check to handle chained renames across multiple migration tags
function resolveRenameChain(
  migrations: WranglerConfig['migrations'] = [],
): Map<string, string> {
  const chain = new Map<string, string>();
  for (const m of migrations) {
    for (const r of m.renamed_classes ?? []) {
      chain.set(r.from, r.to);
    }
  }
  return chain;
}

const renameChain = resolveRenameChain(current.migrations);
for (const cls of removed) {
  const isChainedRename = [...renameChain.keys()].some(
    (from) => from === cls || renameChain.get(from) === cls,
  );
  if (!migratedDeleted.has(cls) && !isChainedRename) {
    errors.push(`'${cls}' removed without a migration entry`);
  }
}
```

## Blocking Merge Without Migration Tag

Add the workflow as a required status check on the branch protection rule or ruleset so the PR cannot be merged when the gate fails:

```yaml
# In repository rulesets (GitHub UI or API):
required_status_checks:
  - context: "validate-migrations"
    app_id: 15368   # GitHub Actions app ID
```

## Anti-patterns
- Running `wrangler deploy --dry-run` as a substitute for migration validation — Wrangler's dry-run does not fully validate migration state against the live namespace registry.
- Using `fetch-depth: 0` to get the full history when only `HEAD~1` is needed; this slows down shallow-clone performance on large repos.
- Skipping the gate on `wrangler.toml`-only changes and relying on deploy-time errors to catch migration gaps.
- Declaring a migration `tag` that was already used in a previous deployment — tags must be globally unique per worker; duplicates cause silent no-ops.

## Gotchas
- The Cloudflare API does not expose the current highest migration tag; maintain a `LAST_MIGRATION_TAG` file in the repository or read it from the live worker's metadata via the Workers API before generating the next tag.
- `sqlite_classes` (Durable Objects with SQLite storage) require their own migration entry distinct from standard class migrations — the validation script must check both `new_sqlite_classes` and `new_classes`.
- A rename followed immediately by a delete in the same deployment requires two separate migration tags, not one compound entry.
- `fetch-depth: 2` fails on the first commit of a new repository; add a guard: `git rev-parse HEAD~1 2>/dev/null || true`.

## Verification
1. Add a new Durable Objects class to `wrangler.toml` bindings without a migration entry; open a PR and confirm the gate job fails.
2. Add the correct `[[migrations]]` block; rerun the job and confirm it passes.
3. Simulate a rename by removing the old class and adding the new one; verify the script accepts a `renamed_classes` entry and rejects a bare remove-and-add without one.

## Related
- `github-actions-cloudflare-d1-migration-pipeline.md`
- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-oidc-cloudflare-deploy.md`
- `github-required-status-checks.md`

## Sources
- https://developers.cloudflare.com/durable-objects/reference/durable-objects-migrations/
- https://developers.cloudflare.com/workers/wrangler/configuration/#migrations
- https://github.com/cloudflare/wrangler-action
