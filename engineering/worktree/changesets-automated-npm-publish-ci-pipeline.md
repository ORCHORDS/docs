# Changesets Automated npm Publish CI Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project ships several internal npm packages (shared types, Cloudflare bindings helpers, UI primitives) from its pnpm monorepo. Without automation, publishing requires a developer to manually run `pnpm changeset version` + `pnpm publish -r`, which causes version drift, forgotten changelogs, and broken package consumers. The goal is a GitHub Actions pipeline where merging a changeset PR automatically bumps versions, updates `CHANGELOG.md`, tags the commit, and publishes to the npm registry — with zero manual `npm publish` steps.

---

## Context

[Changesets](https://github.com/changesets/changesets) uses intent files (`.changeset/*.md`) checked into the PR branch. A dedicated GitHub Actions bot (`@changesets/action`) detects these files, opens a "Version Packages" PR that applies all pending bumps, and — once that PR merges — publishes to npm. The example project monorepo adds two constraints: (1) Cloudflare Workers packages must **not** be published to npm (they are deployed via Wrangler), and (2) the internal shared packages must publish to the GitHub Packages registry, not the public npm registry.

---

## Initial Changesets Setup

```bash
pnpm add -Dw @changesets/cli

# Initialise — creates .changeset/config.json
pnpm changeset init
```

Edit `.changeset/config.json` to reflect the monorepo topology:

```jsonc
{
  "$schema": "https://unpkg.com/@changesets/config@3.0.0/schema.json",
  "changelog": "@changesets/changelog-github",
  "commit": false,
  "fixed": [],
  "linked": [],
  "access": "restricted",
  "baseBranch": "main",
  "updateInternalDependencies": "patch",
  "ignore": [
    "@example project/worker-api",
    "@example project/worker-assets",
    "@example project/worker-cron"
  ]
}
```

The `ignore` list covers the Wrangler-deployed Workers, preventing accidental npm publishes of server-side-only packages.

---

## Developer Workflow: Creating a Changeset

When a developer changes a publishable package they open a changeset before raising a PR:

```bash
# Interactive — prompts for affected packages and bump level
pnpm changeset

# Non-interactive (useful in scripts / AI-assisted PRs)
pnpm changeset add --no-empty <<'EOF'
---
"@example project/ui": minor
"@example project/shared-types": patch
---

Add `useWaspTheme` hook and export `WorkerContext` type.
EOF
```

The generated `.changeset/<hash>.md` is committed alongside the feature code.

---

## GitHub Actions: Version PR Bot

The bot job runs on every push to `main` and either creates or updates the "Version Packages" PR:

```yaml
# .github/workflows/changesets.yml
name: Changesets

on:
  push:
    branches: [main]

concurrency:
  group: changesets-${{ github.ref }}
  cancel-in-progress: true

jobs:
  version-or-publish:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      packages: write       # GitHub Packages publish
      id-token: write       # npm provenance

    steps:
      - uses: actions/checkout@v4
        with:
          # Full history so changeset version can detect which packages changed
          fetch-depth: 0
          token: ${{ secrets.CHANGESETS_BOT_TOKEN }}

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          registry-url: https://npm.pkg.github.com
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Create Version PR or Publish
        uses: changesets/action@v1
        with:
          version:  pnpm changeset version
          publish:  pnpm changeset publish
          title:    "chore: version packages"
          commit:   "chore: version packages"
          createGithubReleases: true
        env:
          GITHUB_TOKEN:    ${{ secrets.CHANGESETS_BOT_TOKEN }}
          NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          NPM_TOKEN:       ${{ secrets.GITHUB_TOKEN }}
```

---

## Package-level Publish Config

Each publishable package's `package.json` must declare the GitHub Packages registry and scope:

```jsonc
// packages/ui/package.json
{
  "name": "@example project/ui",
  "version": "1.4.0",
  "publishConfig": {
    "registry": "https://npm.pkg.github.com",
    "access": "restricted"
  },
  "main": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "files": ["dist"]
}
```

Workers packages that must never publish should carry `"private": true` in their `package.json` — Changesets respects this regardless of the `ignore` list.

---

## Pre-publish Build Step

Packages must be compiled before publishing. Add a `prepublishOnly` script and ensure Changesets calls it:

```jsonc
// packages/ui/package.json (scripts section)
{
  "scripts": {
    "build":           "tsc -p tsconfig.build.json",
    "prepublishOnly":  "pnpm build"
  }
}
```

Alternatively, drive builds via a root script called by the `publish` command:

```bash
# Root package.json
"scripts": {
  "publish:packages": "pnpm -r --filter './packages/*' build && pnpm changeset publish"
}
```

Then in the workflow: `publish: pnpm publish:packages`.

---

## Verifying a Dry-Run Locally

Before merging the Version PR, simulate the publish without pushing to the registry:

```bash
# Apply version bumps to local files only (no git tag, no publish)
pnpm changeset version

# Check what would be published
pnpm changeset publish --dry-run
```

Inspect the output for any Workers packages that should be in the `ignore` list but are not.

---

## Anti-patterns

- **Committing changeset files with `commit: true`** — this writes a commit per changeset during `version`, polluting `git log` and making blame archaeology harder. Keep `commit: false` and let the Version PR be the single audit record.
- **Using the default `npmjs` registry for internal packages** — GitHub Packages scoped to the org prevents accidental public exposure of internal APIs.
- **Skipping `fetch-depth: 0`** — Changesets compares git history to determine changed packages; a shallow clone produces incorrect diff output and may skip packages that should be bumped.
- **Publishing without building** — the `prepublishOnly` hook is the safety net; omitting it ships empty `dist/` directories.
- **Running `pnpm changeset publish` manually from a local machine** — bypasses CI provenance attestation and can publish with local `.env` secrets inadvertently in the build.

---

## Gotchas

- The `CHANGESETS_BOT_TOKEN` must be a PAT with `repo` + `write:packages` scopes — `GITHUB_TOKEN` cannot open PRs against the same repo it is running in (GitHub limitation as of 2026).
- `createGithubReleases: true` creates one GitHub Release per published package tag. In a large monorepo this can create noise; set to `false` and manage releases through `release-please` if you prefer unified release notes.
- `pnpm changeset version` modifies `pnpm-lock.yaml` (internal dependency version bumps) — the Version PR will always contain a lockfile diff, which is expected and correct.
- Packages with `"private": true` are silently skipped by `changeset publish` even if listed in the changeset file — this is correct behaviour, not a bug.
- GitHub Packages requires consumers to add `@example project:registry=https://npm.pkg.github.com` to their `.npmrc` and authenticate. Document this in the package README.

---

## Verification

```bash
# 1. List pending changesets
pnpm changeset status

# 2. Confirm ignored packages are excluded
pnpm changeset status 2>&1 | grep -E "worker-(api|assets|cron)" && echo "ERROR: Workers in changeset" || echo "OK"

# 3. Verify published versions on GitHub Packages
gh api /orgs/example project-app/packages?package_type=npm \
  --jq '.[].name' | sort

# 4. Check npm dist-tag after publish
npm dist-tag ls @example project/ui --registry https://npm.pkg.github.com
```

---

## Related

- `changesets-ci-enforcement-gate-workers.md`
- `conventional-commits-monorepo-changesets-2026.md`
- `monorepo-versioning-independent-releases.md`
- `pnpm-workspace-protocol-version-resolution.md`
- `release-please-semantic-release.md`
- `semantic-release-automation.md`

---

## Sources

- https://github.com/changesets/changesets/blob/main/docs/intro-to-using-changesets.md
- https://github.com/changesets/action
- https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-npm-registry
- https://pnpm.io/filtering
- https://docs.npmjs.com/generating-provenance-statements
