# pnpm publishConfig: Monorepo Package Visibility Rules

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

In the example project monorepo you have three categories of packages:

1. **Internal-only** packages (e.g. `@example project/types`, `@example project/testing-utils`) that
   must never be published to npm.
2. **Publishable libraries** (e.g. `@example project/sdk`) that are `private: false` in
   production but must have their `dist/` directory and correct `exports` map
   when published, not the `src/` used during workspace development.
3. **Cloudflare Workers** apps that are never packages at all.

Without an explicit strategy, `pnpm publish` from a CI pipeline either publishes
every package (catastrophic) or refuses to publish any (because `private: true`
is set globally).

---

## Context

npm's `package.json` supports a `publishConfig` field that overrides specific
fields at publish time. pnpm inherits this and extends it. Key overridable
fields:

| Field | Common use |
|---|---|
| `publishConfig.access` | `"public"` for scoped packages on npm |
| `publishConfig.directory` | Publish from `dist/` instead of root |
| `publishConfig.exports` | Point to built files, not `src/` |
| `publishConfig.main` / `module` | Swap dev entrypoints for dist entrypoints |
| `publishConfig.registry` | Override npm registry per-package |

pnpm additionally reads `publishConfig.directory` during `pnpm pack` to
determine the publish root, enabling the "dual package" pattern without a build
script that copies `package.json`.

---

## Marking packages as never-publish

```jsonc
// packages/testing-utils/package.json
{
  "name": "@example project/testing-utils",
  "private": true,           // ← pnpm publish --recursive skips this
  "version": "0.0.0"
}
```

`private: true` is the canonical guard. pnpm's `--recursive` flag skips
private packages automatically.

For a belt-and-suspenders guard in CI add a `prepublishOnly` script:

```jsonc
{
  "scripts": {
    "prepublishOnly": "echo 'This package is not publishable' && exit 1"
  }
}
```

---

## Publishing from `dist/` with publishConfig.directory

```jsonc
// packages/sdk/package.json
{
  "name": "@example project/sdk",
  "version": "1.4.2",
  "private": false,
  "main": "src/index.ts",        // ← used by workspace (ts-node / tsx)
  "exports": {
    ".": {
      "import": "./src/index.ts",
      "require": "./src/index.cts"
    }
  },
  "publishConfig": {
    "access": "public",
    "directory": "dist",         // ← pnpm publish uses dist/ as the root
    "exports": {                 // ← overrides exports field in the published pkg
      ".": {
        "import": "./index.mjs",
        "require": "./index.cjs",
        "types": "./index.d.ts"
      }
    },
    "main": "./index.cjs",
    "module": "./index.mjs",
    "types": "./index.d.ts"
  }
}
```

When `pnpm pack` or `pnpm publish` runs, it reads `publishConfig.directory`
and treats `packages/sdk/dist/` as if it were the package root. The built
`dist/package.json` is the `package.json` from the source root with all
`publishConfig.*` keys promoted to top-level.

Build step before publish:

```bash
pnpm turbo run build --filter='@example project/sdk'
# produces: packages/sdk/dist/{index.mjs,index.cjs,index.d.ts}
```

---

## Workspace protocol and published references

Inside the monorepo, packages use the `workspace:` protocol:

```jsonc
// packages/worker-a/package.json
{
  "dependencies": {
    "@example project/sdk": "workspace:*"
  }
}
```

When `pnpm publish` converts the `workspace:*` specifier, it replaces it with
the package's actual version from `package.json`. This works correctly
regardless of `publishConfig.directory`. Verify the conversion:

```bash
pnpm pack --dry-run --filter '@example project/sdk' 2>&1 | grep '"@example project/'
```

---

## Scoped package access rules

Scoped packages (`@example project/*`) are private on npm by default. You must set
`publishConfig.access = "public"` or pass `--access public` at publish time:

```jsonc
{
  "publishConfig": {
    "access": "public"
  }
}
```

Or globally in `.npmrc` at the workspace root:

```ini
# .npmrc
@example project:registry=https://registry.npmjs.org/
access=public
```

For an **internal npm registry** (e.g. Verdaccio, GitHub Packages, Cloudflare
npm registry proxy) set per-package:

```jsonc
{
  "publishConfig": {
    "registry": "https://npm.pkg.github.com",
    "access": "restricted"
  }
}
```

---

## CI publish pipeline with pnpm

```yaml
# .github/workflows/publish.yml
name: Publish packages

on:
  push:
    tags: ['@example project/sdk@*']        # tag-triggered publish

jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write            # for npm provenance
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          registry-url: https://registry.npmjs.org

      - run: pnpm install --frozen-lockfile

      - name: Build publishable packages
        run: pnpm turbo run build --filter='@example project/sdk'

      - name: Publish
        run: |
          pnpm publish \
            --filter '@example project/sdk' \
            --no-git-checks \
            --provenance \
            --access public
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
```

`--no-git-checks` skips the "uncommitted files" guard that pnpm performs by
default — necessary in CI where the `dist/` directory is generated and not
tracked by git.

---

## Inspecting what will be published

Before the first publish, always verify the package tarball contents:

```bash
# Dry-run: list files that would be included
pnpm pack --dry-run --filter '@example project/sdk'

# Produce the actual tarball for manual inspection
pnpm pack --filter '@example project/sdk'
tar -tzf example project-sdk-1.4.2.tgz | sort
```

Check that:
- `src/` files are NOT included (they live in `packages/sdk/src/`, not `dist/`)
- `dist/index.mjs`, `dist/index.cjs`, `dist/index.d.ts` are present
- `package.json` in the tarball has the promoted `publishConfig.*` fields at
  the top level (not nested under `publishConfig`)

---

## `.npmignore` vs `files` field

Prefer the `files` whitelist over `.npmignore` — it is easier to audit:

```jsonc
// packages/sdk/package.json (at the source root, NOT inside dist/)
{
  "files": [
    "dist/**",          // only when NOT using publishConfig.directory
    "!dist/**/*.test.*"
  ]
}
```

When `publishConfig.directory` is set, the `files` field in `dist/package.json`
(i.e. the promoted version) controls the tarball. If `dist/` contains no
`package.json`, pnpm copies the source `package.json` with promoted fields and
applies the `files` list relative to `dist/`.

---

## Anti-patterns

- **Setting `private: true` at the workspace root** without per-package
  overrides — pnpm refuses to publish ALL packages.
- **Forgetting `publishConfig.access: "public"`** for scoped packages — npm
  rejects the publish with a 402 Payment Required error (confusing error
  message).
- **Publishing `src/` TypeScript files** — consumers without a build step will
  break. Always publish compiled JS + `.d.ts`.
- **Using `publishConfig.directory` without running a build first** — pnpm
  publishes whatever is in `dist/` at call time; a missing or stale build
  produces a broken package.
- **Workspace `workspace:*` references in the published tarball** — pnpm
  converts them automatically on publish, but only if you run `pnpm publish`,
  not `npm publish` on the tarball.

---

## Gotchas

- `publishConfig.directory` is a pnpm extension; it is also supported by
  Yarn Berry but NOT by npm's `publish` command. If you ever need to fall back
  to `npm publish`, the directory substitution will not happen.
- pnpm does NOT recursively publish packages inside `publishConfig.directory`.
  If your `dist/` has nested packages, only the top-level one is published.
- `pnpm pack` writes the tarball to the **current working directory**, not to
  `dist/`. If you run it from `packages/sdk/`, the `.tgz` lands in
  `packages/sdk/`.
- Changesets and release-please read `package.json` `version` at the source
  root, not inside `dist/`. Bumping the version in the source is correct.
- GitHub Packages requires the `name` field to match `@<org>/<package>` with
  the org matching your GitHub organisation name exactly (case-sensitive).

---

## Verification

```bash
# 1. Confirm private packages are skipped
pnpm publish --recursive --dry-run 2>&1 | grep 'Skipping.*private'

# 2. Confirm published fields are correct
pnpm pack --dry-run --filter '@example project/sdk' 2>&1 \
  | grep -E '(exports|main|types|access)'

# 3. Validate workspace protocol conversion
pnpm pack --filter '@example project/sdk'
tar -Oxzf example project-sdk-*.tgz package/package.json | jq '.dependencies'
# @example project/* deps should show semver, not "workspace:*"
rm example project-sdk-*.tgz
```

---

## Related

- `documentation/categories/worktree/pnpm-workspace-protocol-version-resolution.md`
- `documentation/categories/worktree/monorepo-versioning-independent-releases.md`
- `documentation/categories/worktree/changesets-automated-npm-publish-ci-pipeline.md`
- `documentation/categories/worktree/semantic-versioning-2026.md`

---

## Sources

- pnpm publishConfig — https://pnpm.io/package_json#publishconfig
- npm publishConfig — https://docs.npmjs.com/cli/v10/configuring-npm/package-json#publishconfig
- pnpm publish CLI reference — https://pnpm.io/cli/publish
- GitHub Packages: working with npm — https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-npm-registry
