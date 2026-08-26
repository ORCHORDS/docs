# Changesets Workers Library Publish

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A monorepo contains both deployable Workers (never published to npm) and shared TypeScript libraries consumed by those Workers.
Accidentally bumping or skipping library versions breaks the Workers that import them, especially across independent release cycles.

## Context
Changesets (`@changesets/cli`) manages multi-package versioning and changelog generation in a pnpm monorepo.
When the monorepo mixes Workers packages (deployed via Wrangler, not published) with utility libraries (published to npm or a private registry), Changesets must be configured to version and publish only the library packages while ignoring Workers deployments.
This requires explicit `private: true` in Worker `package.json` files and a custom Changesets publish script that gates on package visibility.

---

## Setup — Repository Layout

```
packages/
  api-worker/          # private: true  — deployed, not published
    package.json
    wrangler.toml
    src/index.ts
  auth-worker/         # private: true  — deployed, not published
    package.json
    wrangler.toml
    src/index.ts
  lib-auth/            # publishable library
    package.json       # no "private" field
    src/index.ts
  lib-d1-helpers/      # publishable library
    package.json
    src/index.ts
  lib-queue-types/     # publishable library
    package.json
    src/index.ts
.changeset/
  config.json
```

```json
// packages/api-worker/package.json  (Worker — never published)
{
  "name": "@example-org/example-repo",
  "version": "0.0.0",
  "private": true,
  "dependencies": {
    "@example-org/example-repo": "workspace:*",
    "@example-org/example-repo": "workspace:*"
  }
}
```

```json
// packages/lib-auth/package.json  (Library — published to npm)
{
  "name": "@example-org/example-repo",
  "version": "1.3.0",
  "exports": {
    ".": {
      "import": "./dist/index.js",
      "types": "./dist/index.d.ts"
    }
  },
  "files": ["dist"],
  "scripts": {
    "build": "tsc --project tsconfig.build.json"
  }
}
```

---

## Section 1 — Changesets Configuration

```json
// .changeset/config.json
{
  "$schema": "https://unpkg.com/@changesets/config@3.0.0/schema.json",
  "changelog": "@changesets/cli/changelog",
  "commit": false,
  "fixed": [],
  "linked": [],
  "access": "restricted",
  "baseBranch": "main",
  "updateInternalDependencies": "patch",
  "ignore": [
    "@example-org/example-repo",
    "@example-org/example-repo"
  ]
}
```

The `ignore` array tells Changesets to skip versioning Workers packages entirely.
`updateInternalDependencies: "patch"` ensures that when `lib-auth` bumps, `api-worker`'s `package.json` version reference stays in sync without triggering a publish.

```typescript
// scripts/changeset-status.ts
// Print a human-readable summary of pending changesets
import { execSync } from 'node:child_process';

const output = execSync('npx changeset status --output=status.json', {
  encoding: 'utf8',
});
console.log(output);

const status = JSON.parse(
  require('node:fs').readFileSync('status.json', 'utf8')
);

for (const pkg of status.releases ?? []) {
  console.log(`${pkg.name}  ${pkg.oldVersion} → ${pkg.newVersion}  (${pkg.type})`);
}
```

---

## Section 2 — Custom Publish Script (Skip Private Packages)

Changesets' default `publish` command respects `private: true`, but a custom script adds pre-publish build validation:

```typescript
// scripts/publish-libraries.ts
import { execSync } from 'node:child_process';
import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

interface PackageJson {
  name: string;
  version: string;
  private?: boolean;
  scripts?: Record<string, string>;
}

function getPackages(dir: string): Array<{ path: string; pkg: PackageJson }> {
  return readdirSync(dir, { withFileTypes: true })
    .filter(e => e.isDirectory())
    .map(e => {
      const pkgPath = resolve(dir, e.name, 'package.json');
      try {
        const pkg: PackageJson = JSON.parse(readFileSync(pkgPath, 'utf8'));
        return { path: resolve(dir, e.name), pkg };
      } catch {
        return null;
      }
    })
    .filter((x): x is NonNullable<typeof x> => x !== null && !x.pkg.private);
}

const packages = getPackages('packages');
console.log(`Publishing ${packages.length} library package(s):`);

for (const { path, pkg } of packages) {
  console.log(`\n--- ${pkg.name}@${pkg.version} ---`);

  // Build before publish
  if (pkg.scripts?.build) {
    console.log('Building...');
    execSync('pnpm build', { cwd: path, stdio: 'inherit' });
  }

  // Dry-run first
  execSync('npm publish --dry-run --access restricted', {
    cwd: path,
    stdio: 'inherit',
  });
}

// Hand off to changesets for actual publish + git tagging
execSync('npx changeset publish', { stdio: 'inherit' });
```

---

## Section 3 — CI Pipeline: Version PR + Publish

```yaml
# .github/workflows/release-libraries.yml
name: Release Libraries

on:
  push:
    branches: [main]

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false   # never cancel a publish in flight

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write        # push version bump commits
      pull-requests: write   # create the "Version Packages" PR
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0     # changesets needs full history

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'
          registry-url: 'https://registry.npmjs.org'

      - run: pnpm install --frozen-lockfile

      - name: Create Version PR or Publish
        id: changesets
        uses: changesets/action@v1
        with:
          publish: npx tsx scripts/publish-libraries.ts
          version: npx changeset version
          commit: 'chore: version library packages'
          title: 'chore: release library packages'
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}

      - name: Trigger Workers re-deploy after library publish
        if: steps.changesets.outputs.published == 'true'
        run: |
          echo "Libraries published — triggering Workers deploy"
          gh workflow run deploy-workers.yml --ref main
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## Anti-patterns

- Forgetting `"ignore"` in `.changeset/config.json` — Changesets will try to bump and publish Workers packages, failing because they have `"private": true` mid-run
- Using `workspace:*` in library-to-library dependencies without `updateInternalDependencies` — library consumers get an unresolvable `workspace:` protocol on npm
- Running `changeset publish` without building first — distributes stale `dist/` from a previous version
- Sharing the same `NPM_TOKEN` for both dry-run jobs and actual publish jobs — a malformed dry-run can leak the token in logs

## Gotchas

- `pnpm publish` requires `--no-git-checks` when run inside a detached HEAD (common in CI); the Changesets action handles this automatically when invoked via `changesets/action`
- `workspace:*` in `package.json` is rewritten to the actual version by `pnpm publish` before the tarball is built — the published package does NOT contain `workspace:` references
- `"access": "restricted"` in Changesets config applies to scoped packages (`@org/pkg`) by default; unscoped packages default to public regardless
- After a library version bump, Workers that use `workspace:*` will still resolve to the new in-repo version immediately without any reinstall — only external consumers need an npm update

## Verification

```bash
# Check pending changesets and which packages will be affected
npx changeset status

# Simulate what a version bump produces without committing
npx changeset version --snapshot canary
git diff packages/lib-auth/package.json
git checkout -- .   # undo the snapshot

# Verify the built package contents before publish
cd packages/lib-auth && pnpm build && npm pack --dry-run

# Confirm Workers packages are excluded from publish
npx changeset status --output=/dev/stdout | grep -v '@example-org/example-repo'
```

## Related

- `changesets-ci-enforcement-gate-workers.md`
- `changesets-automated-npm-publish-ci-pipeline.md`
- `changesets-pre-release-channel-management.md`
- `pnpm-workspace-protocol-version-resolution.md`
- `monorepo-versioning-independent-releases.md`
- `monorepo-wrangler-selective-deploy.md`

## Sources

- https://github.com/changesets/changesets/blob/main/docs/config-file-options.md
- https://github.com/changesets/action
- https://pnpm.io/workspaces#publishing-workspace-packages
- https://developers.cloudflare.com/workers/wrangler/configuration/
- https://docs.npmjs.com/cli/v10/commands/npm-publish
