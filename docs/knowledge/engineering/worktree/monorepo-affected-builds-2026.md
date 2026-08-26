# monorepo-affected-builds-2026

**Issue:** A monorepo team's CI runs every test and builds every package on every PR. As the repo grows from 5 to 50 to 200 packages, CI time balloons from 2 minutes to 40. Developers stop trusting CI, skip waiting, and merge on hope. The team knows "only build what changed" exists but doesn't know how to wire it up correctly.
**Date:** 2026-08-13
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

A monorepo has packages `A` through `Z`. A developer changes a comment in `packages/A`. CI dutifully builds and tests `A` through `Z`, takes 30 minutes, and burns CI minutes the org can't afford. Either nobody waits (merges on green-elsewhere) or everyone waits (velocity tanks). The fundamental problem: CI doesn't know which packages depend on which, so it builds everything to be safe.

## The principle: build only what's affected

Given a change and a dependency graph, "affected" = the changed package + everything that depends on it (transitively). If `A` changed and `B` imports `A`, then `B` must be rebuilt and retested. If `C` has nothing to do with `A`, skip `C`.

This requires:
1. **A dependency graph** the tool can read.
2. **A way to compute the diff** (what changed: vs `main`, vs last commit, vs last green build).
3. **A filter** that runs tasks only on affected packages.

## The 4 tool families in 2026

| Tool | Ecosystem | Mechanism | Notes |
|---|---|---|---|
| **Nx** | JS/TS, polyglot | Project graph + `--affected` | Most mature; works with npm/pnpm/yarn. `nx affected -t build test`. |
| **Turborepo** | JS/TS (Vercel) | Content-hash + `--filter` | Fast caching; `turbo run build --filter=...[origin/main]`. |
| **Bazel** | Polyglot (Google) | Build graphs + remote cache | Enterprise-grade; steep learning curve. Used by Uber, Stripe, etc. |
| **Pants / Buck2** | Python, polyglot | Fine-grained deps | Gaining traction for Python-heavy or mixed-language monorepos. |
| **Gradle + Jib/Maven** | JVM | Module-level up-to-date checks | Native to JVM; lighter than full Bazel for Java/Kotlin shops. |

## Pattern: Turborepo with pnpm (the 2026 JS default)

```jsonc
// turbo.json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": { "dependsOn": ["^build"], "outputs": ["dist/**"] },
    "test":  { "dependsOn": ["^build"], "outputs": [] },
    "lint":  { "outputs": [] }
  }
}
```

```bash
# CI: run only what changed vs main
turbo run build test lint --filter=...[origin/main]
# The "..." prefix means "all packages that depend on changed packages"
# Add `--continue` so one failure doesn't abort the rest (collect all errors)
```

```yaml
# .github/workflows/ci.yml
- run: pnpm install --frozen-lockfile
- run: pnpm exec turbo run build test lint --filter=...[origin/main] --continue
```

## Pattern: Nx affected

```bash
# Detect base automatically (GitHub Actions, GitLab, etc.)
nx affected -t build test lint --base=$BASE_SHA --head=$HEAD_SHA
```

Nx reads `nx.json` + each project's project.json to build the graph. Configure the base SHAs with the `@nrwl/nx-set-shas` action for GitHub Actions to get the correct "last successful build on main" comparison.

## Caching multiplies the speed

Affected detection + remote caching is the killer combo:
- **Local cache**: per-developer, on disk. Re-runs of the same input are instant.
- **Remote cache**: shared across CI runners and developers. Build a package once on CI; every developer's machine and every subsequent CI run skips it.

```bash
# Turborepo: enable remote caching (Vercel-hosted free for small teams)
turbo login
turbo link
# Or self-host with a custom remote cache endpoint
```

Input hashing must include ALL relevant inputs: source files, dependency manifests, env vars, tool versions. A wrong cache key (e.g., forgetting `package.json`) means stale builds. Use the tool's framework-aware hashing rather than rolling your own.

## Gotchas

- **Dependency graph accuracy is everything**: if the tool doesn't know `B` depends on `A`, it won't rebuild `B` when `A` changes, and you ship broken code. Audit the graph periodically (`nx graph` or `turbo dry-run`). The most common break: a package imports another via a path the tool doesn't track (e.g., deep imports bypassing package boundaries).
- **Circular dependencies silently break affected detection**: `A` → `B` → `A`. Tools either error or, worse, compute a wrong affected set. Run a cycle check in CI (`nx graph --file` + a cycle detector).
- **"Changed" vs "last green" base**: comparing to `origin/main` is wrong if main is red — you'd rebuild nothing because the diff includes broken main. Compare to the **last successful commit on main** (Nx's `set-shas`, Turborepo's custom logic). This is the #1 subtle bug in affected setups.
- **Lockfile and config changes should be global**: if `package.json`, `pnpm-lock.yaml`, `tsconfig.json`, or `.github/workflows/*` change, treat the ENTIRE repo as affected. A lockfile bump can break any package. Add explicit "if config changed, build all" logic.
- **Storybook / integration tests spanning packages**: end-to-end tests that exercise multiple packages don't fit the per-package affected model cleanly. Either run E2E on every PR (expensive) or run E2E affected by expanding the affected set to include any package the E2E touches.
- **Cache poisoning is a security risk**: if attackers can write to your remote cache, they can inject malicious build artifacts that your CI will trust. Use a private, authenticated cache; never accept cache entries from untrusted sources. Sign artifacts if your threat model warrants it.
- **Forgetting `--continue`**: by default, most tools stop on the first failure. You get one error, fix it, re-run, hit the next error. Use `--continue` (Turborepo) or `--parallel --max-warnings` patterns to collect all failures in one run.

## Related
- `monorepo-pnpm-turborepo-2026.md`
- `monorepo-build-tools-2026.md`
- `monorepo-ci-parallelization.md`
- `github-actions-reusable-2026.md`
