# pnpm Workspace Protocol Version Resolution

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
A Cloudflare Workers monorepo uses pnpm workspaces. Engineers add internal packages as dependencies using the bare version `"*"` or a concrete semver range like `"^1.2.0"` — which causes the package to resolve from the registry instead of the local workspace copy during development, and breaks `wrangler deploy` because the local changes are not reflected. The fix is the `workspace:` protocol, but the team does not fully understand the semantics of `workspace:*`, `workspace:^`, and `workspace:~`.

## Context
The `workspace:` protocol is a pnpm-specific dependency specifier that instructs pnpm to always resolve a dependency from a local workspace package rather than the registry, regardless of the version published there. It is the correct way to express intra-monorepo dependencies in a pnpm workspace and is distinct from the `catalog:` protocol (which is about shared version pins for *external* packages). When publishing packages to a registry, pnpm rewrites `workspace:*` specifiers into concrete semver ranges — this rewrite step is what makes the protocol safe for both development and publishing.

## workspace: protocol variants

```jsonc
// packages/api-client/package.json
{
  "name": "@example-org/example-repo",
  "version": "1.4.0",
  "dependencies": {
    // workspace:* → during development, use the local version as-is.
    // On publish pnpm rewrites to the exact current version: "1.4.0"
    "@example-org/example-repo": "workspace:*",

    // workspace:^ → on publish, rewrite to "^<current-version>": "^1.4.0"
    "@example-org/example-repo": "workspace:^",

    // workspace:~ → on publish, rewrite to "~<current-version>": "~1.4.0"
    "@example-org/example-repo": "workspace:~",

    // workspace:<range> → on publish, use this exact range literally
    "@example-org/example-repo": "workspace:>=1.0.0"
  }
}
```

## Rewrite behaviour summary

```
┌──────────────────┬───────────────────────────────────┬───────────────────┐
│ Specifier        │ Resolves during development to    │ Rewritten on pub  │
├──────────────────┼───────────────────────────────────┼───────────────────┤
│ workspace:*      │ Local package (any version)       │ "1.4.0" (exact)   │
│ workspace:^      │ Local package (any version)       │ "^1.4.0" (compat) │
│ workspace:~      │ Local package (any version)       │ "~1.4.0" (patch)  │
│ workspace:>=1.0  │ Local package if >=1.0.0          │ ">=1.0.0" literal │
│ workspace:1.4.0  │ Local package if version matches  │ "1.4.0" literal   │
└──────────────────┴───────────────────────────────────┴───────────────────┘
```

## pnpm-workspace.yaml configuration

```yaml
# pnpm-workspace.yaml — at the monorepo root
packages:
  - 'workers/*'
  - 'packages/*'
  - 'tools/*'
```

```bash
# After editing package.json to add a workspace: dep, link it
pnpm install

# Verify the link exists in node_modules
ls -la node_modules/@example-org/example-repo
# lrwxrwxrwx ... -> ../../packages/shared-types

# Confirm pnpm resolved it from workspace, not registry
pnpm why @example-org/example-repo
# @example-org/example-repo 1.4.0
# └─ @example-org/example-repo > @example-org/example-repo@workspace:*
```

## Cloudflare Workers monorepo: typical package structure

```
workers-monorepo/
├── pnpm-workspace.yaml
├── package.json
├── packages/
│   ├── shared-types/          # @example-org/example-repo
│   │   ├── package.json
│   │   └── src/index.ts
│   ├── logger/                # @example-org/example-repo
│   │   ├── package.json
│   │   └── src/index.ts
│   └── config/                # @example-org/example-repo
│       ├── package.json
│       └── src/index.ts
└── workers/
    ├── api-gateway/           # Cloudflare Worker
    │   ├── package.json       # depends on workspace:* packages
    │   └── src/index.ts
    └── auth-worker/
        ├── package.json
        └── src/index.ts
```

```jsonc
// workers/api-gateway/package.json
{
  "name": "@example-org/example-repo",
  "private": true,
  "dependencies": {
    "@example-org/example-repo": "workspace:*",
    "@example-org/example-repo": "workspace:^",
    "@example-org/example-repo": "workspace:~"
  },
  "devDependencies": {
    "wrangler": "catalog:"
  }
}
```

## TypeScript path aliases aligned with workspace packages

When using `workspace:*`, TypeScript must also resolve the package from source (not a compiled `dist/`). Align `tsconfig.json` paths:

```jsonc
// tsconfig.json at monorepo root (base config)
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@example-org/example-repo": ["packages/shared-types/src/index.ts"],
      "@example-org/example-repo":       ["packages/logger/src/index.ts"],
      "@example-org/example-repo":       ["packages/config/src/index.ts"]
    }
  }
}
```

```typescript
// packages/shared-types/package.json — exports field for Node resolution
// must align with the tsconfig paths above
```

```jsonc
// packages/shared-types/package.json
{
  "name": "@example-org/example-repo",
  "version": "1.4.0",
  "main": "./src/index.ts",
  "exports": {
    ".": {
      "types": "./src/index.ts",
      "import": "./src/index.ts",
      "default": "./src/index.ts"
    }
  }
}
```

## Publishing workspace packages with pnpm publish

```bash
# pnpm rewrites workspace: specifiers before publishing to npm registry
# --dry-run shows the rewritten package.json without actually publishing
pnpm publish --dry-run --access public

# Output (rewritten dependencies in the tarball):
# {
#   "dependencies": {
#     "@example-org/example-repo": "1.4.0",    ← was workspace:*
#     "@example-org/example-repo":       "^1.4.0",   ← was workspace:^
#     "@example-org/example-repo":       "~1.4.0"    ← was workspace:~
#   }
# }

# Publish all changed packages in topological order
pnpm -r publish --access public --no-git-checks
```

## CI: validate all intra-monorepo deps use workspace: protocol

```yaml
# .github/workflows/workspace-protocol-check.yml
name: Workspace Protocol Check
on: [pull_request]

jobs:
  check-workspace-protocol:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check for bare-version intra-monorepo deps
        run: |
          node - <<'EOF'
          import { readdirSync, readFileSync, existsSync } from "fs";
          import { join } from "path";

          const WS_PACKAGES = ["@example-org/example-repo", "@example-org/example-repo", "@example-org/example-repo"];
          const WORKERS_DIR = "workers";
          const PACKAGES_DIR = "packages";

          let violations = 0;

          function checkDir(dir) {
            if (!existsSync(dir)) return;
            for (const entry of readdirSync(dir, { withFileTypes: true })) {
              if (!entry.isDirectory()) continue;
              const pkgPath = join(dir, entry.name, "package.json");
              if (!existsSync(pkgPath)) continue;
              const pkg = JSON.parse(readFileSync(pkgPath, "utf8"));
              for (const depSection of ["dependencies", "devDependencies", "peerDependencies"]) {
                const deps = pkg[depSection] ?? {};
                for (const [name, version] of Object.entries(deps)) {
                  if (WS_PACKAGES.includes(name) && !String(version).startsWith("workspace:")) {
                    console.error(`VIOLATION: ${pkg.name} has "${name}": "${version}" — should be "workspace:*"`);
                    violations++;
                  }
                }
              }
            }
          }

          checkDir(WORKERS_DIR);
          checkDir(PACKAGES_DIR);
          process.exit(violations > 0 ? 1 : 0);
          EOF
```

## workspace: vs catalog: choosing the right protocol

```
┌─────────────────┬──────────────────────────────────┬─────────────────────────────┐
│ Protocol        │ Use for                          │ Resolves from               │
├─────────────────┼──────────────────────────────────┼─────────────────────────────┤
│ workspace:*     │ Internal packages in this repo   │ Local workspace package     │
│ catalog:        │ External shared version pins     │ Registry (version from cat) │
│ ^1.2.0          │ External packages (non-catalog)  │ Registry                    │
│ link:../path    │ Local path outside workspace     │ Filesystem path             │
└─────────────────┴──────────────────────────────────┴─────────────────────────────┘
```

## Anti-patterns
- Using `"*"` or `"latest"` for intra-monorepo packages — pnpm will try to resolve from the registry and install a published version instead of the local source.
- Using `"file:../shared-types"` instead of `"workspace:*"` — `file:` creates a copy at install time; changes to the local source require re-running `pnpm install` to pick up; `workspace:*` uses a symlink that reflects changes immediately.
- Adding a workspace package to `catalog:` in addition to using `workspace:*` — catalog is for external version alignment and will conflict with workspace resolution.
- Publishing a Worker package (marked `"private": true`) with `workspace:*` deps without verifying the bundler inlines them — `wrangler` bundles via esbuild and follows symlinks, but third-party bundlers may not.
- Forgetting to update TypeScript `paths` when adding a new workspace package — TypeScript will find the `node_modules` symlink but may load compiled `.js` instead of `.ts` source, causing type errors on source changes.

## Gotchas
- `workspace:*` is only valid in `package.json` files inside the pnpm workspace; running `npm install` or `yarn install` in a workspace subdirectory will reject the specifier with a parse error.
- `pnpm publish` rewrites specifiers automatically, but `pnpm pack` does NOT rewrite them by default before pnpm 8.9.0 — use `pnpm pack --pack-destination` on pnpm >= 8.9.0 or check the release notes for your version.
- Changesets (`@changesets/cli`) understands `workspace:*` natively when using `pnpm publish`; however, if you run `changeset publish` directly without `pnpm`, the rewrite does not happen.
- `pnpm install --frozen-lockfile` in CI will fail if `workspace:*` dependencies are added to `package.json` without updating `pnpm-lock.yaml` locally first — the lockfile must always be committed with the `package.json` change.
- If two workspace packages depend on each other in a cycle, pnpm resolves the cycle but TypeScript will fail with a circular reference error unless you break the cycle at the type level.

## Verification
```bash
# Confirm workspace symlinks are in place
ls -la node_modules/@orchords/

# Confirm pnpm resolves from workspace (not registry)
pnpm why @example-org/example-repo | grep workspace

# Dry-run publish to see rewritten specifiers
pnpm publish --dry-run 2>&1 | grep -A 20 '"dependencies"'

# Confirm frozen lockfile passes after package.json change
pnpm install --frozen-lockfile
```

## Related
- [pnpm-catalog-monorepo-dependency-alignment.md](pnpm-catalog-monorepo-dependency-alignment.md)
- [monorepo-pnpm-turborepo-2026.md](monorepo-pnpm-turborepo-2026.md)
- [git-submodule-vs-pnpm-workspace-workers-packages.md](git-submodule-vs-pnpm-workspace-workers-packages.md)
- [monorepo-package-boundary-enforcement-workers.md](monorepo-package-boundary-enforcement-workers.md)
- [monorepo-workspace-cloudflare-workers.md](monorepo-workspace-cloudflare-workers.md)

## Sources
- https://pnpm.io/workspaces#workspace-protocol-workspace
- https://pnpm.io/package_json#publishconfig
- https://pnpm.io/cli/publish
- https://github.com/changesets/changesets/blob/main/docs/working-with-workspaces.md
