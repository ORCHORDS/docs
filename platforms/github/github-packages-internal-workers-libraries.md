# GitHub Package Registry for Internal Cloudflare Workers Libraries

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A platform team builds shared utilities — authentication middleware, Cloudflare KV helpers,
typed D1 query builders, R2 presigned-URL generators — that multiple Workers need. Copy-pasting
these across repos causes drift. Publishing them to npm public registry exposes internal
implementation details. The team wants a private npm registry that GitHub Actions can publish
to and consume from without maintaining a separate registry service.

## Context

GitHub Packages provides a scoped npm registry at `https://npm.pkg.github.com`. Every
repository in an organisation can publish packages scoped to `@{org}` and consume them using
the standard npm/pnpm protocol. For Workers projects, this solves the "shared lib" problem
without Cloudflare-specific overhead.

Key characteristics of GitHub Packages for Workers projects:
- Packages are scoped to the GitHub org or user (`@myorg/workers-auth`)
- Access is controlled by repository permissions and PATs / GITHUB_TOKEN
- `GITHUB_TOKEN` can publish from Actions without any secrets management
- Consuming repos need `NODE_AUTH_TOKEN` set to a PAT with `read:packages` scope
- The registry URL must appear in `.npmrc` — it is not auto-configured

Workers-specific concerns:
- Shared packages must be **tree-shakeable** and **ESM-first** — Workers runtimes do not
  support CommonJS in the same way Node.js does
- `wrangler.toml` does not know about npm scopes; the resolution happens entirely in Node.js
  during the build step before Wrangler bundles the Worker
- Type declarations (`.d.ts`) must be published alongside the ESM output for Workers-typed
  environments to pick up the correct `ExecutionContext`, `KVNamespace`, etc. types

## Section 1: Library Package Setup for Workers ESM Output

```json
// packages/workers-auth/package.json
{
  "name": "@myorg/workers-auth",
  "version": "1.3.0",
  "description": "Shared authentication middleware for Cloudflare Workers",
  "type": "module",
  "main": "./dist/index.js",
  "module": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "exports": {
    ".": {
      "import": "./dist/index.js",
      "types": "./dist/index.d.ts"
    },
    "./kv": {
      "import": "./dist/kv.js",
      "types": "./dist/kv.d.ts"
    }
  },
  "files": [
    "dist/",
    "!dist/**/*.test.js",
    "!dist/**/*.test.d.ts"
  ],
  "publishConfig": {
    "registry": "https://npm.pkg.github.com",
    "access": "restricted"
  },
  "peerDependencies": {
    "@cloudflare/workers-types": ">=4.0.0"
  },
  "devDependencies": {
    "@cloudflare/workers-types": "^4.20260101.0",
    "typescript": "^5.7.0",
    "wrangler": "^3.101.0"
  }
}
```

```jsonc
// packages/workers-auth/tsconfig.json
{
  "compilerOptions": {
    "target": "ESNext",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "lib": ["ESNext"],
    // Workers-specific: use the workers-types lib instead of DOM
    "types": ["@cloudflare/workers-types"],
    "strict": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "outDir": "dist",
    "rootDir": "src"
  },
  "include": ["src/**/*"],
  "exclude": ["src/**/*.test.ts", "dist"]
}
```

The `"type": "module"` and `"exports"` map are critical for Workers compatibility. Wrangler
uses an esbuild bundler that resolves the `import` condition. If the package only exports
`main` (CommonJS), Wrangler may bundle it incorrectly, introducing `require()` calls into
the Worker bundle that fail at runtime.

## Section 2: Publish Workflow with Automatic Version and Changelog

```yaml
# .github/workflows/publish-package.yml
name: Publish Workers Library

on:
  push:
    tags:
      - 'workers-auth/v*'   # Tag format: workers-auth/v1.3.0
  workflow_dispatch:
    inputs:
      package:
        description: 'Package name (directory under packages/)'
        required: true
        type: string
      bump:
        description: 'Version bump type'
        required: true
        type: choice
        options: [patch, minor, major]

permissions:
  contents: write    # Create release
  packages: write    # Publish to GitHub Packages

jobs:
  publish:
    runs-on: ubuntu-latest
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
          registry-url: 'https://npm.pkg.github.com'
          scope: '@myorg'

      - name: Install dependencies
        run: pnpm install --frozen-lockfile

      # Determine which package to publish (from tag or manual input)
      - name: Resolve package
        id: pkg
        run: |
          if [[ "${{ github.event_name }}" == "push" ]]; then
            TAG="${{ github.ref_name }}"
            PKG="${TAG%%/v*}"
            VERSION="${TAG#*/v}"
          else
            PKG="${{ inputs.package }}"
            cd "packages/${PKG}"
            CURRENT=$(node -p "require('./package.json').version")
            BUMP="${{ inputs.bump }}"
            # Simple semver bump
            IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT"
            case "$BUMP" in
              major) VERSION="$((MAJOR+1)).0.0" ;;
              minor) VERSION="${MAJOR}.$((MINOR+1)).0" ;;
              patch) VERSION="${MAJOR}.${MINOR}.$((PATCH+1))" ;;
            esac
            cd -
          fi
          echo "pkg=${PKG}" >> "$GITHUB_OUTPUT"
          echo "version=${VERSION}" >> "$GITHUB_OUTPUT"
          echo "dir=packages/${PKG}" >> "$GITHUB_OUTPUT"

      - name: Bump version in package.json
        if: github.event_name == 'workflow_dispatch'
        working-directory: ${{ steps.pkg.outputs.dir }}
        run: |
          npm version "${{ steps.pkg.outputs.version }}" --no-git-tag-version

      - name: Build library
        working-directory: ${{ steps.pkg.outputs.dir }}
        run: pnpm build

      - name: Run tests before publish
        working-directory: ${{ steps.pkg.outputs.dir }}
        run: pnpm test

      - name: Publish to GitHub Packages
        working-directory: ${{ steps.pkg.outputs.dir }}
        env:
          NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          npm publish --access restricted

      - name: Create GitHub Release
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          PKG="${{ steps.pkg.outputs.pkg }}"
          VERSION="${{ steps.pkg.outputs.version }}"
          gh release create "${PKG}/v${VERSION}" \
            --title "${PKG} v${VERSION}" \
            --generate-notes \
            --repo "${{ github.repository }}"

      # Commit the version bump back to main if triggered manually
      - name: Commit version bump
        if: github.event_name == 'workflow_dispatch'
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add "packages/${{ steps.pkg.outputs.pkg }}/package.json"
          git commit -m "chore: release ${{ steps.pkg.outputs.pkg }}@${{ steps.pkg.outputs.version }}"
          git push origin HEAD:main
```

## Section 3: Consuming the Package in a Worker Repository

Consumer repos need a `.npmrc` pointing at the GitHub Packages registry for the `@myorg` scope,
plus a PAT secret with `read:packages` permission.

```ini
# .npmrc (committed to repo, no secrets here)
@myorg:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${NPM_AUTH_TOKEN}
```

```yaml
# .github/workflows/ci.yml (consuming Worker repo)
name: Worker CI

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          # The registry-url here configures NODE_AUTH_TOKEN for the global registry,
          # but our .npmrc overrides the scope. We still need to set the variable.
          registry-url: 'https://npm.pkg.github.com'
          scope: '@myorg'

      - name: Install deps (including internal packages)
        env:
          # For GitHub Actions in the same org, GITHUB_TOKEN works if the package
          # repo has "Allow GitHub Actions to create and approve pull requests" enabled.
          # For cross-org or fine-grained access, use a dedicated PAT.
          NODE_AUTH_TOKEN: ${{ secrets.GH_PACKAGES_READ_TOKEN }}
        run: pnpm install --frozen-lockfile

      - name: Build and type-check
        run: pnpm tsc --noEmit && pnpm build

      - name: Deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          NODE_AUTH_TOKEN: ${{ secrets.GH_PACKAGES_READ_TOKEN }}
        run: pnpm wrangler deploy --env production
```

Local development setup for engineers:

```bash
# One-time setup: authenticate with GitHub Packages
echo "//npm.pkg.github.com/:_authToken=ghp_YOUR_PAT" >> ~/.npmrc
# Or use gh CLI:
gh auth token | \
  node -e "const t=require('fs').readFileSync('/dev/stdin','utf8').trim(); \
  require('fs').appendFileSync(process.env.HOME+'/.npmrc', \
  '//npm.pkg.github.com/:_authToken='+t+'\n')"

# Then install as normal
pnpm install
```

## Anti-patterns

- **Publishing as `public` access** — GitHub Packages scoped to an org are private by default.
  Using `--access public` on a package containing internal business logic exposes it to the
  public npm mirror.
- **Using a personal PAT with `write:packages` in CI** — use `GITHUB_TOKEN` for publishing
  from Actions within the same org. A personal PAT tied to one engineer's account breaks when
  they leave the org.
- **Shipping CommonJS output** — Workers runtimes on the Cloudflare edge expect ESM. A
  CommonJS-only package forces Wrangler to shim `require()`, which is not always available
  and adds bytes to the bundle. Always set `"type": "module"` and `"exports"`.
- **Including `node_modules` in `files`** — a misconfigured `package.json` `files` array that
  includes `node_modules/` causes npm to publish the entire dependency tree, making the package
  many megabytes. Always include only `dist/`.
- **No peer dependency on `@cloudflare/workers-types`** — if the library uses `KVNamespace`,
  `R2Bucket`, or other Worker globals in its type signatures but does not declare a peer
  dependency on `@cloudflare/workers-types`, consumers get `Cannot find type...` errors when
  the type version drifts.

## Gotchas

- **`GITHUB_TOKEN` publish scope is the current repo only** — `GITHUB_TOKEN` in a workflow for
  repo `myorg/workers-auth` can publish packages **owned by that repo**. It cannot publish
  packages owned by a different repository. If your monorepo publishes multiple packages from
  one Actions workflow, all packages must be owned by that one repository.
- **Package versions are immutable** — once `@myorg/workers-auth@1.3.0` is published, you
  cannot republish to the same version. You must bump the version. Use `npm publish --dry-run`
  in CI to verify the package contents before the real publish.
- **GitHub Packages npm registry does not support `npm search`** — `pnpm add @myorg/` tab
  completion and `npm search` do not work against the GitHub registry. Maintain an internal
  wiki or use `gh api` to list packages.
- **`wrangler deploy` does not install npm packages** — the npm install step must complete
  before `wrangler deploy` runs. If the Worker's `package.json` references `@myorg/workers-auth`
  and `NODE_AUTH_TOKEN` is not set during the deploy step, install will succeed (from cache)
  but a cold build in a fresh container will fail.
- **`declarationMap: true` in tsconfig is required for Go-to-definition** — without source
  maps for type declarations, IDE users navigating to a type inside the shared package see
  the compiled `.d.ts` file instead of the source TypeScript.

## Verification

```bash
# List packages published by the org
gh api /orgs/{org}/packages?package_type=npm \
  --jq '.[].name'

# List versions of a specific package
gh api /orgs/{org}/packages/npm/workers-auth/versions \
  --jq '.[].name'

# Download and inspect package contents (without installing)
npm pack @myorg/workers-auth --registry https://npm.pkg.github.com
tar -tzf myorg-workers-auth-*.tgz | head -40

# Verify ESM exports are present
node --input-type=module <<'EOF'
import { createAuthMiddleware } from '@myorg/workers-auth';
console.log(typeof createAuthMiddleware);
EOF

# Check the package is tree-shakeable by inspecting Wrangler bundle size
wrangler deploy --dry-run --outdir dist-check
du -sh dist-check/
```

## Related

- `github-packages-npm-registry.md` — general npm registry on GitHub Packages
- `github-packages-container-registry-ghcr.md` — Docker images for Workers build environments
- `github-actions-cloudflare-deploy-workflow.md` — consuming these packages in a deploy pipeline
- `github-actions-cache-invalidation-workers-builds.md` — caching the node_modules that include these packages
- `github-fine-grained-personal-access-tokens.md` — creating PATs with minimal `read:packages` scope
- `github-apps-installation-tokens.md` — using GitHub App tokens instead of PATs for package access

## Sources

- https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-npm-registry
- https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions
- https://developers.cloudflare.com/workers/wrangler/bundling/
- https://nodejs.org/api/packages.html#package-entry-points
- https://www.typescriptlang.org/tsconfig#declarationMap
