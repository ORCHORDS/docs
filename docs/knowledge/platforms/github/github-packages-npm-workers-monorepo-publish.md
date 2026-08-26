# GitHub Packages NPM Registry for Cloudflare Workers Monorepo

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

The example project / example.com backend is split across multiple Cloudflare Workers that share utility packages: a cryptographic signing library for anonymous identity tokens, a typed D1 query builder, and a shared Zod schema collection. Without a private registry these packages must be copy-pasted between Workers or made public on npmjs.com — neither option is acceptable for an anonymous social platform where internal implementation details should remain private.

## Context

GitHub Packages hosts a scoped npm registry at `https://npm.pkg.github.com` that publishes packages to an organisation namespace. Packages are readable by anyone with a `read:packages` scope (or `GITHUB_TOKEN` in Actions), and publishable with `write:packages`. For a Cloudflare Workers monorepo using pnpm workspaces, the CI pipeline can publish on every merge to `main` and Workers can consume the latest package versions via a `.npmrc` that redirects the org scope to the GitHub registry.

## Configuring the Registry in the Monorepo

Create a root `.npmrc` that routes only the org-scoped packages to GitHub Packages while leaving the public registry intact:

```ini
# .npmrc (root of monorepo)
@example project:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}
```

Each publishable package needs a `package.json` with the scoped name and `publishConfig`:

```json
{
  "name": "@example project/identity-tokens",
  "version": "1.4.2",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "publishConfig": {
    "registry": "https://npm.pkg.github.com",
    "access": "restricted"
  },
  "files": ["dist"]
}
```

## Publish Workflow

The CI workflow publishes packages only when version tags are pushed, preventing accidental publishes from feature branches:

```yaml
# .github/workflows/publish-packages.yml
name: Publish NPM Packages

on:
  push:
    tags:
      - "packages/identity-tokens/v*"
      - "packages/d1-query/v*"
      - "packages/schemas/v*"

jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          registry-url: "https://npm.pkg.github.com"
          scope: "@example project"

      - name: Install dependencies
        run: pnpm install --frozen-lockfile

      - name: Determine package from tag
        id: pkg
        run: |
          TAG="${{ github.ref_name }}"
          # tag format: packages/identity-tokens/v1.4.2
          PKG_DIR=$(echo "$TAG" | cut -d'/' -f1-2)
          echo "dir=$PKG_DIR" >> "$GITHUB_OUTPUT"

      - name: Build package
        working-directory: ${{ steps.pkg.outputs.dir }}
        run: pnpm build

      - name: Publish to GitHub Packages
        working-directory: ${{ steps.pkg.outputs.dir }}
        run: pnpm publish --no-git-checks
        env:
          NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Consuming Published Packages in Workers

Each Cloudflare Worker that depends on an internal package installs it as a normal npm dependency. The repo-level `.npmrc` handles authentication when running `pnpm install` locally (with a developer PAT) or in CI (with `GITHUB_TOKEN`).

```yaml
# .github/workflows/deploy-feed-worker.yml (relevant auth section)
- uses: actions/setup-node@v4
  with:
    node-version: "20"
    registry-url: "https://npm.pkg.github.com"
    scope: "@example project"

- name: Install
  run: pnpm install --frozen-lockfile
  env:
    NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

- name: Deploy
  run: pnpm wrangler deploy
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

In `apps/feed/package.json`:

```json
{
  "dependencies": {
    "@example project/identity-tokens": "^1.4.0",
    "@example project/schemas": "^2.1.0"
  }
}
```

## Versioning Strategy with Changesets

Manual version bumping across many packages is error-prone. The Changesets tool (`@changesets/cli`) integrates with the publish workflow:

```yaml
# .github/workflows/version-or-publish.yml
name: Version or Publish

on:
  push:
    branches: [main]

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      packages: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          registry-url: "https://npm.pkg.github.com"
          scope: "@example project"

      - run: pnpm install --frozen-lockfile
        env:
          NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Create release PR or publish
        uses: changesets/action@v1
        with:
          publish: pnpm changeset publish
          version: pnpm changeset version
          title: "chore: version packages"
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Changesets opens a "Version Packages" PR when changesets are present. Merging that PR triggers the actual publish.

## Anti-patterns

- Publishing from feature branches; always gate publishes on `main` or a version tag.
- Hardcoding a personal access token in `.npmrc` — use `${GITHUB_TOKEN}` as a variable and supply it from Actions secrets.
- Setting `"access": "public"` in `publishConfig` for packages that contain internal API shape or token formats.
- Relying on `npm publish` instead of `pnpm publish` in a pnpm workspace — the workspace `node_modules` layout confuses npm's pack step.
- Omitting `--frozen-lockfile` in CI installs, which silently upgrades transitive deps and breaks reproducibility.

## Gotchas

- `GITHUB_TOKEN` for `packages: write` only has permission within the repository that owns the workflow, not across org repos. Cross-repo package access requires a PAT with `read:packages` stored as a repository secret.
- The `setup-node` action writes a temporary `.npmrc` in the home directory that overrides the repo-level `.npmrc`; the `registry-url` and `scope` parameters must match exactly what is in `publishConfig`.
- GitHub Packages does not support `npm unpublish` after 24 hours; a mispublished package with sensitive data requires a GitHub Support ticket.
- Package visibility cannot be changed from private to public after first publish for organisation packages.
- Wrangler bundles all `node_modules` at build time (for Workers with `nodejs_compat`), so the package must be a CommonJS or ESM module compatible with the Workers runtime — no Node-only APIs.

## Verification

1. Merge a changeset to `main` and confirm Changesets opens a "Version Packages" PR.
2. Merge the version PR and confirm `pnpm changeset publish` runs without error; check `https://github.com/orgs/example project-app/packages` for the new version.
3. In a Worker repo, run `pnpm add @example project/identity-tokens@latest` and verify it resolves from `npm.pkg.github.com`.
4. Deploy the Worker with `wrangler deploy` and confirm the bundled script includes the package contents (check `wrangler deploy --dry-run --outdir dist`).

## Related

- `github-packages-npm-registry.md`
- `github-packages-internal-workers-libraries.md`
- `github-actions-reusable-workflows-workers-deploy.md`
- `github-actions-monorepo-strategy.md`
- `github-fine-grained-personal-access-tokens.md`

## Sources

- https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-npm-registry
- https://github.com/changesets/changesets/blob/main/docs/intro-to-using-changesets.md
- https://pnpm.io/workspaces
- https://developers.cloudflare.com/workers/wrangler/bundling/
