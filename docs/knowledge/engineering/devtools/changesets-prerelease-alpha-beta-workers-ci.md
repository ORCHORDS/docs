# Changesets Pre-release (Alpha / Beta / RC) for Workers CI Publishing

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

You maintain a shared Workers library (e.g., a Hono middleware, a D1 query builder) in a pnpm monorepo. Before publishing a stable major release you want to publish `1.0.0-alpha.1`, `1.0.0-beta.1`, `1.0.0-rc.1` to npm so downstream teams can test. The standard `changesets` release workflow publishes stable versions only; the pre-release workflow requires entering and exiting a "pre-release mode" that most teams configure incorrectly.

---

## Context

Changesets pre-release mode (`changeset pre enter <tag>`) locks the repository into a state where every `changeset version` produces a pre-release version string. The pre-release state is tracked in `.changeset/pre.json`. CI must detect this file and adjust the publish command accordingly.

This article covers:
- Entering and exiting pre-release mode
- CI workflow for alpha/beta channels
- Publishing to npm with a dist-tag
- Coordinating with Wrangler deploy gating

Stack:

- `@changesets/cli` ^2.27
- `pnpm` workspaces
- GitHub Actions
- `wrangler` ^4.0 (for deploy gating after publish)

---

## Entering Pre-release Mode

```bash
# One-time, on a feature branch (e.g., next or v2-alpha)
pnpm changeset pre enter alpha
# Creates .changeset/pre.json — commit this file
git add .changeset/pre.json
git commit -m "chore: enter alpha pre-release mode"
```

`.changeset/pre.json` after entering:

```json
{
  "mode": "pre",
  "tag": "alpha",
  "initialVersions": {
    "@myorg/workers-middleware": "0.9.3"
  },
  "changesets": []
}
```

While in pre mode, every `changeset add` accumulates changesets **without bumping** the version. Only `changeset version` reads them and produces `1.0.0-alpha.1`, `1.0.0-alpha.2`, etc.

---

## Adding Changesets in Pre-release Mode

```bash
# Normal workflow — add a changeset describing the change
pnpm changeset add
# Select: @myorg/workers-middleware | major | "New fetch handler API (breaking)"
```

When you run `pnpm changeset version` next:

```bash
pnpm changeset version
# Produces: @myorg/workers-middleware@1.0.0-alpha.1
```

Each subsequent `changeset version` call increments the pre-release counter:
`1.0.0-alpha.1` → `1.0.0-alpha.2` → …

---

## GitHub Actions Release Workflow

`.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    branches:
      - main
      - "next"          # pre-release branch
      - "v*-alpha"      # e.g., v2-alpha
      - "v*-beta"

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: false

jobs:
  release:
    name: Release
    runs-on: ubuntu-latest
    permissions:
      contents: write
      id-token: write   # for npm provenance
      pull-requests: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
          registry-url: "https://registry.npmjs.org"

      - name: Install dependencies
        run: pnpm install --frozen-lockfile

      - name: Detect pre-release mode
        id: prerelease
        run: |
          if [ -f ".changeset/pre.json" ]; then
            TAG=$(jq -r '.tag' .changeset/pre.json)
            echo "is_prerelease=true" >> "$GITHUB_OUTPUT"
            echo "dist_tag=$TAG" >> "$GITHUB_OUTPUT"
          else
            echo "is_prerelease=false" >> "$GITHUB_OUTPUT"
            echo "dist_tag=latest" >> "$GITHUB_OUTPUT"
          fi

      - name: Create Release PR or publish (stable)
        if: steps.prerelease.outputs.is_prerelease == 'false'
        uses: changesets/action@v1
        with:
          publish: pnpm changeset publish
          title: "chore: version packages"
          commit: "chore: version packages"
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}

      - name: Version and publish (pre-release)
        if: steps.prerelease.outputs.is_prerelease == 'true'
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
          DIST_TAG: ${{ steps.prerelease.outputs.dist_tag }}
        run: |
          git config user.email "ci@myorg.com"
          git config user.name "CI Bot"
          pnpm changeset version
          pnpm changeset publish --tag "$DIST_TAG" --no-git-tag
          git add -A
          git commit -m "chore: publish pre-release packages" || true
          git push
```

Key decisions:
- Stable releases use `changesets/action` which creates a "Version Packages" PR then publishes on merge.
- Pre-release runs `version` + `publish` directly on every push (no intermediary PR) because pre-release iterations move fast.
- `--no-git-tag` avoids cluttering the tag list with `v1.0.0-alpha.1`, `v1.0.0-alpha.2`, etc.

---

## Publishing to a Dist-tag

```bash
# Manual publish during development
pnpm changeset publish --tag alpha

# Consumer installs the alpha channel
pnpm add @myorg/workers-middleware@alpha

# View all published dist-tags
npm dist-tag ls @myorg/workers-middleware
# alpha: 1.0.0-alpha.7
# latest: 0.9.3
```

When the pre-release is stable, exit pre mode and publish to `latest`:

```bash
pnpm changeset pre exit
git add .changeset/pre.json
git commit -m "chore: exit pre-release mode"
# Open a normal release PR — changesets/action takes over
```

---

## Gating Wrangler Deploy on Pre-release Publish

For Workers that consume your own pre-release library:

```yaml
# In the consumer Worker's deploy workflow
- name: Install with pre-release channel
  run: pnpm add @myorg/workers-middleware@alpha

- name: Build Worker
  run: pnpm build

- name: Deploy to preview environment
  run: pnpm wrangler deploy --env preview
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

This pattern lets QA test the alpha library inside a real Workers environment before any stable release.

---

## Anti-patterns

- **Committing `.changeset/pre.json` to main**: Pre mode is branch-specific. If it lands on `main`, every release from main becomes a pre-release until someone notices and runs `changeset pre exit`.
- **Running `changeset version` manually while CI also does it**: Double-versioning produces `1.0.0-alpha.1-alpha.1`. Let CI own the version step exclusively.
- **Using `--tag latest` for a pre-release publish**: This overwrites the `latest` dist-tag and breaks consumers running `pnpm add @myorg/workers-middleware` (they get the alpha). Always specify a non-`latest` tag.
- **Forgetting `--frozen-lockfile` after `changeset version` bumps `package.json`**: `changeset version` modifies `package.json` version fields. The lockfile becomes out of sync. Re-run `pnpm install` (not `--frozen-lockfile`) as part of the version step in CI.
- **Using `changesets/action` for pre-releases**: The action creates a "Version Packages" PR on pre-release branches too, which adds noise. The direct `version` + `publish` approach is cleaner for rapid pre-release iteration.

---

## Gotchas

- `pre.json` tracks which changesets have been consumed. If you cherry-pick or rebase changesets while in pre mode, `pre.json` may reference changeset IDs that no longer exist, causing `changeset version` to error. Fix: delete the orphaned IDs from `pre.json` manually.
- The `changesets/action` does not support `--tag` for publish; passing `publish: "pnpm changeset publish --tag alpha"` works but the action still tries to create a "Version Packages" PR, which is redundant for pre-releases.
- `--no-git-tag` suppresses git tags but `changesets/action` also creates a GitHub Release for each published version. On pre-release branches where you run the action, disable GitHub Release creation with `createGithubReleases: false`.
- npm's `dist-tag` for `alpha` is package-scoped. If your monorepo has 5 packages, each gets its own `alpha` dist-tag independently. They do not share a single pre-release counter.
- After `changeset pre exit`, the next `changeset version` produces the stable version (e.g., `1.0.0`), consuming all accumulated changesets from the pre-release phase. This is the correct behavior — do not re-add changesets for the final stable release.

---

## Verification

```bash
# Confirm pre.json state
cat .changeset/pre.json | jq '{mode, tag}'

# Preview what version would be produced
pnpm changeset version --dry-run

# Confirm dist-tag after publish
npm view @myorg/workers-middleware dist-tags

# Confirm consumer can install
pnpm add @myorg/workers-middleware@alpha --dry-run
```

---

## Related

- `changesets-monorepo-versioning.md`
- `changesets-versioning.md`
- `pnpm-workspace-setup.md`
- `pnpm-catalogs-version-policy.md`
- `renovate-major-version-grouping-workers-monorepo.md`
- `wrangler-config-validation-ci.md`

---

## Sources

- Changesets pre-release docs: https://github.com/changesets/changesets/blob/main/docs/prereleases.md
- `changesets/action` GitHub Action: https://github.com/changesets/action
- npm dist-tags: https://docs.npmjs.com/cli/v10/commands/npm-dist-tag
- npm provenance with OIDC: https://docs.npmjs.com/generating-provenance-statements
- Wrangler deploy environments: https://developers.cloudflare.com/workers/wrangler/environments/
