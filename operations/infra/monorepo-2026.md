# monorepo-2026

**Issue:** Monorepo — Turborepo vs Nx vs pnpm
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have 5 apps + 10 shared packages. CI builds
everything. Deps are out of sync. The team is
frustrated. You wish you had a monorepo tool.

## Root cause
**Without orchestration, monorepo is chaos.** Pick
the right tool.

**Source:** Digital Applied 2026 + anhtu.dev 2026.

## The "monorepo vs polyrepo" pattern

For choice:
| Dim | Monorepo | Polyrepo |
|---|---|---|
| Dep sync | Single lockfile | Drift easy |
| CI/CD | Affected detection | Simple |
| Git perf | Needs sparse | Each light |
| Team auto | Module boundaries | Full |

The monorepo is per scale.

## The "when to use monorepo" pattern

For yes:
- 2+ apps sharing code
- UI library across frontends
- Multiple packages published
- Atomic commits (UI + API)
- Shared tooling config

The threshold is 2+ apps.

## The "Turborepo" pattern

For Turborepo:
- **Type:** Build orchestrator
- **Version:** 2.x
- **Scale:** 2-20 packages
- **Lang:** JS/TS only
- **Cache:** Built-in (HMAC)
- **Remote cache:** Vercel (free) or self-host
- **Setup:** Low (single turbo.json)
- **Cost:** Free

The Turborepo is the default.

## The "Nx" pattern

For Nx:
- **Type:** Build system + workspace manager
- **Version:** 22
- **Scale:** 20+ packages, 10-500+ engineers
- **Lang:** JS/TS + .NET, Java, Go (plugins)
- **Cache:** Named inputs
- **Remote cache:** Nx Cloud (paid)
- **Setup:** Medium
- **Strengths:** Code gen, project graph

The Nx is enterprise.

## The "pnpm workspaces" pattern

For pnpm:
- **Type:** Package manager
- **Symlink:** Content-addressable store
- **Disk:** 40-70% less than npm
- **Workspaces:** Yes
- **Build:** No (need Turbo/Nx)
- **Catalogs:** pnpm 9.5+

The pnpm is the standard.

## The "Bazel" pattern

For Bazel:
- **Type:** Build system
- **Scale:** 1000+ engineers
- **Lang:** Polyglot
- **Setup:** Very high (Starlark)
- **Strengths:** Hermetic, action-based
- **Use:** Google-scale

The Bazel is for 1000+.

## The "decision matrix" pattern

For choice:
| Size | Pick |
|---|---|
| Small (3-20), JS/TS | pnpm + Turborepo |
| Medium (10-100) | pnpm + Nx |
| Enterprise (100+), polyglot | Bazel or Nx + plugins |
| > 1000 engineers | Bazel |

The decision is per size.

## The "Turborepo config" pattern

For turbo.json:
```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": [".next/**", "dist/**", "build/**"],
      "cache": true
    },
    "dev": {
      "cache": false,
      "persistent": true
    },
    "test": {
      "dependsOn": ["^build"],
      "cache": true
    },
    "lint": {
      "cache": true
    }
  },
  "remoteCache": {
    "enabled": true
  }
}
```

The config is single.

## The "Turborepo commands" pattern

For commands:
```bash
turbo build              # All packages
turbo build lint         # Parallel
turbo build --filter=@myapp/web
turbo build --filter=...@myapp/web  # + deps
turbo build --since=main  # Only changed
```

The filter is per need.

## The "remote cache" pattern

For cache:
- **Vercel:** Free tier
- **Self-host:** S3 + token
- **CI reduction:** 60-80%
- **Team-wide:** Share

The cache is the win.

## The "pnpm catalogs" pattern

For dedup:
```yaml
# pnpm-workspace.yaml
packages:
  - "apps/*"
  - "packages/*"

catalogs:
  react: ^18.3.0
  typescript: ^5.6.0
  next: ^15.0.0
```

The catalog is central.

## The "package.json with catalog" pattern

For ref:
```json
{
  "dependencies": {
    "react": "catalog:",
    "typescript": "catalog:"
  }
}
```

The ref is `"catalog:"`.

## The "apps vs packages" pattern

For structure:
```
monorepo/
├── apps/
│   ├── web/         # Next.js
│   ├── api/         # Hono
│   └── admin/
├── packages/
│   ├── ui/          # Shared React
│   ├── database/    # Drizzle
│   ├── config/      # TS, ESLint
│   └── utils/
├── turbo.json
├── pnpm-workspace.yaml
```

The structure is split.

## The "no circular dep" pattern

For deps:
- **Apps import packages:** Yes
- **Packages import apps:** No
- **Rule:** Prevents cycles

The dep is one-way.

## The "shared config" pattern

For config:
```json
// packages/web/tsconfig.json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "outDir": "./dist"
  }
}
```

The config is extended.

## The "versioning fixed vs independent" pattern

For versioning:
- **Fixed:** All packages, one version, internal
- **Independent:** Per package, published, multiple
- **Changesets:** Supports both
- **Nx release:** Supports both

The choice is per need.

## The "git sparse checkout" pattern

For DX:
```bash
git clone --filter=blob:none --sparse \
  https://github.com/myorg/monorepo.git
cd monorepo
git sparse-checkout set apps/web packages/ui
```

The checkout is per need.

## The "affected-only CI" pattern

For CI:
```yaml
- run: turbo build --filter=...[origin/main]
# Only changed + deps
```

The CI is per PR.

## The "no CODEOWNERS" anti-pattern

For no owners:
- **Issue:** No accountability
- **Fix:** CODEOWNERS per package

The owners are required.

## The "no remote cache" anti-pattern

For no cache:
- **Issue:** CI is 30 min
- **Fix:** Vercel or self-host

The cache is required.

## The "too granular" anti-pattern

For too many:
- **Issue:** 50 packages for sake of it
- **Fix:** 3-5, grow naturally

The count is minimal.

## The "no pnpm" anti-pattern

For npm/Yarn:
- **Issue:** Duplicate React, slow
- **Fix:** pnpm with hoisting

The pnpm is default.

## The "no turbo/nx" anti-pattern

For raw scripts:
- **Issue:** No caching, no deps
- **Fix:** Turborepo or Nx

The orchestrator is required.

## The "no sparse checkout" anti-pattern

For full clone:
- **Issue:** Slow, large
- **Fix:** Sparse for large repos

The sparse is per need.

## The "monorepo checklist" pattern

For checklist:
- [ ] pnpm workspaces
- [ ] Turborepo (or Nx)
- [ ] turbo.json configured
- [ ] Remote cache enabled
- [ ] pnpm catalogs
- [ ] apps/ + packages/ structure
- [ ] No cycles
- [ ] Shared config at root
- [ ] CODEOWNERS per package
- [ ] Affected-only CI
- [ ] Sparse checkout docs

The checklist is 11.

## Verification
- **Test:** Build works
- **Test:** Cache hit
- **Test:** Affected only
- **Test:** No cycles
- **Audit:** Quarterly

## Gotchas
- **The "no remote cache" anti-pattern.** Enable.
- **The "too granular" anti-pattern.** 3-5 first.
- **The "no CODEOWNERS" anti-pattern.** Required.

## Related
- `infra/iac-best-practices.md`
- `infra/iac-testing-2026.md`
- `infra/arc-github-runners-k8s.md`
- `worktree/conventional-commits.md`
- `github/branch-protection-and-codeowners.md`
- Digital Applied: https://www.digitalapplied.com/blog/monorepo-strategy-2026-turborepo-nx-decision-matrix
- anhtu.dev: https://anhtu.dev/monorepo-2026-turborepo-nx-pnpm-workspaces-large-teams-1124
- PkgPulse: https://www.pkgpulse.com/guides/javascript-monorepos-2026-best-practices-pitfalls
