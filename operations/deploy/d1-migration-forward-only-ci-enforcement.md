# D1 Migration Forward-Only CI Enforcement

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A developer opens a PR that modifies an existing migration file rather than adding a new one. Another developer's PR deletes a migration to "clean up" the history before a release. Both changes corrupt the migration ledger: D1 has already applied the file at its original checksum, and re-applying after modification silently diverges the schema from what the migrations record. You need CI to catch and block these mutations before they reach a shared environment.

## Context

D1 uses a sequential, file-based migration model managed by Wrangler. Applied migrations are tracked in a `d1_migrations` table on the database with a `name` column matching the filename. Wrangler checks for unapplied files by comparing filenames — it does not verify the content checksum of already-applied migrations. This means:

- Editing an applied migration file does not trigger a re-apply.
- Deleting a migration file removes it from the source-of-truth without rolling back the schema.
- Renaming breaks the filename linkage, causing the renamed file to be re-applied as if new.

Forward-only enforcement means: once a migration file is merged to the main branch, its content and name are immutable. Schema changes require a new migration file.

## Detecting Mutations with Git Diff in CI

The canonical check compares the PR's changed files against the set of migration files that already exist on the base branch. Any migration that is deleted or whose content is modified — but was not newly added in this PR — is a violation.

```typescript
// scripts/check-forward-only-migrations.ts
import { execSync } from 'child_process';
import { readFileSync, existsSync } from 'fs';
import { createHash } from 'crypto';
import { join } from 'path';

const MIGRATIONS_DIR = 'migrations';
const BASE_BRANCH = process.env.BASE_BRANCH ?? 'origin/main';

function sha256(content: string): string {
  return createHash('sha256').update(content).digest('hex');
}

function runGit(cmd: string): string {
  return execSync(cmd, { encoding: 'utf8' }).trim();
}

interface Violation {
  file: string;
  reason: 'deleted' | 'modified';
}

function checkForwardOnly(): void {
  // Get the list of migration files that exist on the base branch
  const baseFiles = runGit(`git ls-tree --name-only ${BASE_BRANCH} -- ${MIGRATIONS_DIR}`)
    .split('\n')
    .filter((f) => f.endsWith('.sql'));

  // Get git diff status for migration files between base and HEAD
  const diffOutput = runGit(
    `git diff --name-status ${BASE_BRANCH}...HEAD -- ${MIGRATIONS_DIR}`
  );

  const violations: Violation[] = [];

  if (diffOutput === '') {
    console.log('✓ No migration file changes detected');
    return;
  }

  const diffLines = diffOutput.split('\n').filter(Boolean);

  for (const line of diffLines) {
    const [status, ...fileParts] = line.split('\t');
    const filePath = fileParts[fileParts.length - 1];

    // Added files are fine — they are new migrations
    if (status === 'A') {
      console.log(`✓ New migration: ${filePath}`);
      continue;
    }

    // Deleted migration
    if (status === 'D') {
      violations.push({ file: filePath, reason: 'deleted' });
      continue;
    }

    // Modified migration (M = modified, R = renamed, C = copied with modifications)
    if (status.startsWith('M') || status.startsWith('R') || status.startsWith('C')) {
      // Only flag modifications to files that existed on base — not new files renamed within the PR
      const basename = fileParts[0]; // for renames, fileParts[0] is the old name
      if (baseFiles.some((f) => f.includes(basename) || f.includes(filePath))) {
        violations.push({ file: filePath, reason: 'modified' });
      }
    }
  }

  if (violations.length > 0) {
    console.error('\nForward-only migration violations detected:\n');
    for (const v of violations) {
      console.error(`  ${v.reason.toUpperCase()}: ${v.file}`);
      console.error(
        v.reason === 'deleted'
          ? '    → Create a compensating migration (DROP/ALTER) instead of deleting this file.'
          : '    → Revert this change and create a new migration file for the schema change.'
      );
    }
    console.error('\nAll schema changes must be expressed as new migration files. Never edit or delete applied migrations.');
    process.exit(1);
  }

  console.log('✓ All migration changes are forward-only');
}

checkForwardOnly();
```

## Content Checksum Registry

For stronger guarantees, maintain a checksum registry file that records the SHA-256 of every migration at the time it was first merged. CI validates that each existing migration's current content matches its registered checksum.

```typescript
// scripts/generate-migration-registry.ts
import { readdirSync, readFileSync, writeFileSync } from 'fs';
import { createHash } from 'crypto';
import { join } from 'path';

const MIGRATIONS_DIR = 'migrations';
const REGISTRY_FILE = '.migration-registry.json';

type Registry = Record<string, string>; // filename -> sha256

function buildRegistry(): Registry {
  const files = readdirSync(MIGRATIONS_DIR)
    .filter((f) => f.endsWith('.sql'))
    .sort();

  const registry: Registry = {};
  for (const file of files) {
    const content = readFileSync(join(MIGRATIONS_DIR, file), 'utf8');
    registry[file] = createHash('sha256').update(content).digest('hex');
  }
  return registry;
}

writeFileSync(REGISTRY_FILE, JSON.stringify(buildRegistry(), null, 2) + '\n');
console.log(`✓ Registry written to ${REGISTRY_FILE}`);
```

```typescript
// scripts/verify-migration-registry.ts
import { readFileSync, readdirSync } from 'fs';
import { createHash } from 'crypto';
import { join } from 'path';

const MIGRATIONS_DIR = 'migrations';
const REGISTRY_FILE = '.migration-registry.json';

type Registry = Record<string, string>;

function verifyRegistry(): void {
  const registry: Registry = JSON.parse(readFileSync(REGISTRY_FILE, 'utf8'));
  const violations: string[] = [];

  for (const [filename, expectedHash] of Object.entries(registry)) {
    const filePath = join(MIGRATIONS_DIR, filename);
    try {
      const content = readFileSync(filePath, 'utf8');
      const actualHash = createHash('sha256').update(content).digest('hex');
      if (actualHash !== expectedHash) {
        violations.push(
          `MODIFIED: ${filename}\n  expected: ${expectedHash}\n  actual:   ${actualHash}`
        );
      }
    } catch {
      violations.push(`DELETED: ${filename} (was in registry, no longer on disk)`);
    }
  }

  // Also check for files on disk that aren't in the registry (new files — OK, just log)
  const diskFiles = readdirSync(MIGRATIONS_DIR).filter((f) => f.endsWith('.sql')).sort();
  for (const file of diskFiles) {
    if (!registry[file]) {
      console.log(`  NEW (not yet in registry): ${file}`);
    }
  }

  if (violations.length > 0) {
    console.error('\nMigration integrity violations:\n');
    violations.forEach((v) => console.error(v));
    console.error('\nRun `npm run registry:update` on main after merging new migrations.');
    process.exit(1);
  }

  console.log(`✓ All ${Object.keys(registry).length} registered migrations are unmodified`);
}

verifyRegistry();
```

## GitHub Actions Enforcement

```yaml
# .github/workflows/migration-guard.yml
name: Migration Forward-Only Guard

on:
  pull_request:
    paths:
      - 'migrations/**'

jobs:
  guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Required for git diff against base branch

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - run: npm ci

      - name: Check forward-only constraint
        run: npx tsx scripts/check-forward-only-migrations.ts
        env:
          BASE_BRANCH: origin/${{ github.base_ref }}

      - name: Verify checksum registry
        run: npx tsx scripts/verify-migration-registry.ts

  # Separate job: update registry only on main branch merges
  update-registry:
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
      - run: npm ci
      - name: Regenerate registry
        run: npx tsx scripts/generate-migration-registry.ts
      - name: Commit updated registry
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add .migration-registry.json
          git diff --staged --quiet || git commit -m "chore: update migration registry [skip ci]"
          git push
```

## Naming Convention Enforcement

Enforce sequential timestamp prefixes to prevent ordering ambiguity:

```typescript
// scripts/check-migration-naming.ts
import { readdirSync } from 'fs';

const MIGRATIONS_DIR = 'migrations';
// Expected format: 0001_description.sql, 0002_add_users.sql, etc.
const MIGRATION_PATTERN = /^(\d{4})_[a-z0-9_]+\.sql$/;

function checkNaming(): void {
  const files = readdirSync(MIGRATIONS_DIR)
    .filter((f) => f.endsWith('.sql'))
    .sort();

  const violations: string[] = [];
  const seenNumbers = new Set<number>();

  for (const file of files) {
    const match = file.match(MIGRATION_PATTERN);
    if (!match) {
      violations.push(`BAD NAME: "${file}" — must match pattern: NNNN_description.sql`);
      continue;
    }
    const num = parseInt(match[1], 10);
    if (seenNumbers.has(num)) {
      violations.push(`DUPLICATE NUMBER: ${file} — number ${match[1]} already used`);
    }
    seenNumbers.add(num);
  }

  // Check for gaps
  const sorted = [...seenNumbers].sort((a, b) => a - b);
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] !== sorted[i - 1] + 1) {
      violations.push(`GAP: missing migration number between ${sorted[i - 1]} and ${sorted[i]}`);
    }
  }

  if (violations.length > 0) {
    violations.forEach((v) => console.error(v));
    process.exit(1);
  }
  console.log(`✓ ${files.length} migrations correctly named and sequenced`);
}

checkNaming();
```

## Anti-patterns

- **Squashing migration commits during PR merge** — safe for application code, but if a developer adds migration `0005` and then amends it in a follow-up commit, squashing can change the migration content from what was reviewed without triggering a new CI run on the final content.
- **Using `.sql` file timestamps as migration identifiers** — clock skew between developer machines causes ordering conflicts. Use a sequential counter prefix generated by a script.
- **Storing the checksum registry outside version control** — the registry must be committed alongside the migrations; an external store is a separate failure domain.

## Gotchas

- `git diff --name-status` uses tab separators, not spaces. Shell `awk` and TypeScript string splits must account for `\t`.
- Wrangler's `d1 migrations apply` does not validate checksums — the enforcement is entirely in CI. Bypassing CI (e.g., direct push to main) skips the guard. Protect your main branch with required status checks.
- The registry update job commits to main via `git push`. If branch protection requires PRs, use a bot token with bypass permission or route the commit through a separate bot PR.

## Verification

```bash
# Simulate a violation locally
cp migrations/0001_init.sql migrations/0001_init.sql.bak
echo "-- tampered" >> migrations/0001_init.sql
npx tsx scripts/verify-migration-registry.ts
# Expected: MODIFIED: 0001_init.sql ... exit 1

# Restore
mv migrations/0001_init.sql.bak migrations/0001_init.sql

# Verify clean state
npx tsx scripts/verify-migration-registry.ts
# Expected: ✓ All N registered migrations are unmodified
```

## Related

- `d1-migration-dry-run-ci-gate.md`
- `d1-migration-rollback-automated-detection.md`
- `d1-schema-migration-sequencing-wrangler-remote.md`
- `d1-zero-downtime-schema-migration-workers-compatibility.md`

## Sources

- Wrangler D1 migrations commands: https://developers.cloudflare.com/workers/wrangler/commands/#d1-migrations
- D1 migration file format: https://developers.cloudflare.com/d1/reference/migrations/
- GitHub Actions path filters: https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#onpushpull_requestpull_request_targetpathspaths-ignore
