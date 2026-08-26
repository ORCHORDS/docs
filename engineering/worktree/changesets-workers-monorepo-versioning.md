# Changesets for Versioning and Changelogs in a Workers Monorepo

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Workers monorepo containing multiple packages publishes independently versioned workers to production. Without a structured versioning tool, version bumps are done manually, changelogs go out of date, and inter-package semver relationships are ignored. Changesets automates the entire flow: developers declare intent at PR time, CI bumps versions and writes changelogs, and publish triggers `wrangler deploy` for every changed package in dependency order.

---

## Context

Changesets is a versioning and changelog management tool designed for monorepos. Each changeset is a small markdown file committed alongside the code change; it records which packages are affected and the semver bump type (`patch`, `minor`, `major`). A CI job collects pending changesets, runs `npx changeset version` to bump `package.json` files and write `CHANGELOG.md` entries, then commits those changes back to the repository. A second CI job — triggered by the version bump commit — runs `npx changeset publish`, which for Workers packages executes `wrangler deploy` instead of `npm publish`. GitHub Release notes are created automatically from the changelog content, giving stakeholders a structured record of every deployment.

---

## Section 1 — Changesets Installation and Config

```bash
# Install changesets in the monorepo root
npm install --save-dev @changesets/cli

# Initialise changesets (creates .changeset/ directory)
nx changeset init
# or
npx changeset init
```

```json
// .changeset/config.json
{
  "$schema": "https://unpkg.com/@changesets/config@3.0.0/schema.json",
  "changelog": "@changesets/cli/changelog",
  "commit": false,
  "fixed": [],
  "linked": [
    ["@my-org/api-gateway", "@my-org/auth-service"]
  ],
  "access": "restricted",
  "baseBranch": "main",
  "updateInternalDependencies": "patch",
  "ignore": []
}
```

```bash
# Developer workflow: add a changeset when opening a PR
npx changeset add
# ? Which packages would you like to include?
#   ◉ @my-org/api-gateway
#   ◯ @my-org/auth-service
#   ◯ @my-org/media-worker
# ? What kind of change is this for @my-org/api-gateway?
#   ○ patch
#   ● minor
#   ○ major
# ? Please enter a summary for this change:
#   Add pagination support to orders endpoint
# Changeset added: .changeset/teal-horses-jump.md

# The generated changeset file
cat .changeset/teal-horses-jump.md
```

```markdown
---
"@my-org/api-gateway": minor
---

Add pagination support to the orders endpoint with `limit` and `cursor` query parameters.
```

---

## Section 2 — CI Versioning Job

```yaml
# .github/workflows/changesets-version.yml
name: Version Packages

on:
  push:
    branches:
      - main

permissions:
  contents: write
  pull-requests: write

jobs:
  version:
    name: Version and Changelog
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - name: Install dependencies
        run: npm ci

      - name: Create Release PR or apply versions
        uses: changesets/action@v1
        with:
          version: npx changeset version
          commit: "chore(release): version packages"
          title: "chore(release): version packages"
          createGithubReleases: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

```typescript
// scripts/changeset-publish.ts
// Custom publish script: runs wrangler deploy instead of npm publish
import { execSync } from 'child_process';
import { readdirSync, readFileSync } from 'fs';
import { join } from 'path';

interface PackageJson {
  name: string;
  version: string;
  scripts?: Record<string, string>;
  private?: boolean;
}

const PACKAGES_DIR = join(process.cwd(), 'packages');

function getPackages(): Array<{ name: string; dir: string; pkg: PackageJson }> {
  return readdirSync(PACKAGES_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => {
      const dir = join(PACKAGES_DIR, d.name);
      const pkg: PackageJson = JSON.parse(
        readFileSync(join(dir, 'package.json'), 'utf8')
      );
      return { name: pkg.name, dir, pkg };
    })
    .filter(({ pkg }) => !pkg.private);
}

function deployPackage(dir: string, name: string, version: string): void {
  console.log(`\n=== Deploying ${name}@${version} ===`);
  execSync('npx wrangler deploy --env production', {
    cwd: dir,
    stdio: 'inherit',
    env: {
      ...process.env,
      CLOUDFLARE_API_TOKEN: process.env.CLOUDFLARE_API_TOKEN,
    },
  });
  console.log(`Deployed ${name}@${version} successfully.`);
}

for (const { name, dir, pkg } of getPackages()) {
  deployPackage(dir, name, pkg.version);
}
```

---

## Section 3 — Publish Job and GitHub Releases

```yaml
# .github/workflows/changesets-publish.yml
name: Publish Packages

on:
  push:
    branches:
      - main
    paths:
      - 'packages/**/package.json'
      - 'packages/**/CHANGELOG.md'

permissions:
  contents: write
  id-token: write

jobs:
  publish:
    name: Deploy Workers and Create Releases
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - name: Install dependencies
        run: npm ci

      - name: Deploy changed Workers packages
        run: npx tsx scripts/changeset-publish.ts
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

      - name: Create GitHub Releases from changelogs
        uses: changesets/action@v1
        with:
          publish: echo "publish-step-handled-above"
          createGithubReleases: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

```bash
# Manually trigger a publish (dry run to verify)
npx changeset status
# @my-org/api-gateway@1.3.0 (minor) — Add pagination support
# @my-org/auth-service@1.3.0 (linked minor)

# Confirm which packages would be deployed
npx tsx scripts/changeset-publish.ts --dry-run 2>&1 | grep 'Deploying'
```

---

## Anti-patterns

- **Running `npx changeset version` locally and pushing manually** — this bypasses the CI-generated version commit and breaks the Release PR workflow; always let the CI job drive versioning on `main`.
- **Using `"commit": true` in `config.json`** — this makes changesets auto-commit during `changeset version`, which conflicts with the `changesets/action` CI step that manages the commit itself.
- **Linking unrelated packages** — the `linked` array in `config.json` forces all listed packages to share the same version number; only link packages that are always released together (e.g., a client and its types package).
- **Storing `CLOUDFLARE_API_TOKEN` in cleartext** — the token must be set as a GitHub Actions encrypted secret; never hard-code it in `wrangler.toml` or commit it to the repository.

---

## Gotchas

- The `changesets/action` creates a "Version Packages" PR rather than directly committing to `main`; merging that PR is what triggers the publish workflow — do not close it without merging.
- `wrangler deploy` does not honour `npm publish` semantics; the custom `changeset-publish.ts` script is required because Changesets's built-in publish step calls `npm publish` by default.
- If a Worker has no `wrangler.toml`, the deploy script will fail silently; add a guard that checks for the file's existence before calling `wrangler deploy`.
- The `linked` array synchronises versions but not changelogs; each linked package still gets its own `CHANGELOG.md` entry, which is the correct behaviour for monorepos.
- `npx changeset status` exits `0` even when there are no pending changesets; use `npx changeset status --since=origin/main` to detect whether a PR has a changeset and fail CI if it does not.
- GitHub Releases created by `changesets/action` are tied to git tags of the form `package-name@version`; ensure your tag protection rules allow the bot token to push these tags.

---

## Verification

```bash
# Confirm changesets are present for open PRs
npx changeset status --since=origin/main

# Confirm package.json versions were bumped correctly
jq .version packages/api-gateway/package.json
jq .version packages/auth-service/package.json

# Confirm CHANGELOG.md was updated
head -20 packages/api-gateway/CHANGELOG.md

# Confirm each Worker is deployed
curl -sf https://api-gateway.example.workers.dev/version | jq .version
curl -sf https://auth-service.example.workers.dev/version | jq .version

# Confirm GitHub Releases exist
gh release list --limit 5
```

---

## Related

- `git-worktree-monorepo-package-parallel-dev.md`
- `git-worktree-hotfix-production-parallel.md`

---

## Sources

- Changesets Documentation — https://github.com/changesets/changesets
- Changesets Action — https://github.com/changesets/action
- Wrangler Deploy Reference — https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- Cloudflare Workers Environments — https://developers.cloudflare.com/workers/wrangler/environments/
