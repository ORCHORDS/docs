# Monorepo Team Topology: Ownership in a pnpm Workspace

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Your Cloudflare Workers project started as a single package. Then you added a shared
types package. Then a UI component library. Then a second Worker. Now you have five
packages under `packages/`, two Workers under `workers/`, and a Next.js app under
`apps/`, all in one repository managed with pnpm workspaces. Nobody is sure who owns
what. A PR that changes a shared utility breaks three downstream packages. Deployments
require manual coordination because two Workers share code that has no declared owner.

This article is about making team ownership explicit in a pnpm workspace at startup
scale, before the coordination costs become a tax on shipping velocity.

---

## Context

A pnpm workspace monorepo offers genuine advantages for a Cloudflare Workers stack:
- Shared TypeScript types between Workers, front-end, and tests
- Single `pnpm install` reproduces the full dependency tree
- Turborepo or Nx can build and test only the packages affected by a change
- Wrangler can consume shared packages from the workspace as local dependencies

The risk is that the structural benefits (shared code) create invisible ownership
ambiguity (shared responsibility = no responsibility). This is a social problem, not a
technical one. The technical tools (CODEOWNERS, package.json fields, Turborepo
pipeline) only work if backed by explicit team agreements.

This article assumes:
- pnpm workspaces
- Turborepo for build orchestration (or similar)
- GitHub for version control and PR review
- A team of 2–8 engineers

---

## Section 1 — Package Taxonomy

Before assigning ownership, agree on what kinds of packages exist in your workspace.
Use a consistent directory structure that makes the taxonomy self-documenting.

**Recommended structure:**
```
/
├── apps/
│   ├── web/            # Front-end application (Next.js / SvelteKit)
│   └── dashboard/      # Internal tools
├── workers/
│   ├── api/            # Primary API Worker
│   └── cron/           # Scheduled jobs Worker
├── packages/
│   ├── ui/             # Shared React/Svelte components
│   ├── config/         # Shared ESLint, TypeScript, Tailwind configs
│   ├── database/       # D1 schema, migrations, query helpers
│   ├── types/          # Shared TypeScript interfaces and enums
│   └── utils/          # Shared business-logic utilities
└── tooling/
    ├── scripts/        # Deployment and release scripts
    └── testing/        # Shared test fixtures and helpers
```

Rules:
- `apps/` and `workers/` are deployable units. They have a single clear owner.
- `packages/` are library packages consumed by apps and workers. They need explicit
  declared owners because they cross deployment boundaries.
- `tooling/` is owned by whoever manages CI/CD (often the most senior engineer).

---

## Section 2 — CODEOWNERS as the Source of Truth

GitHub CODEOWNERS (`.github/CODEOWNERS`) makes ownership enforceable, not just
documented. A CODEOWNERS entry requires review from the named owner before a PR can
merge (when branch protection is configured).

Example `.github/CODEOWNERS`:
```
# Deployable units — product team owners
/apps/web/                  @your-org/frontend-team
/apps/dashboard/            @your-org/ops-team
/workers/api/               @your-org/backend-team
/workers/cron/              @your-org/backend-team

# Shared packages — explicitly owned, not "everyone's"
/packages/ui/               @your-org/frontend-team
/packages/config/           @your-org/platform
/packages/database/         @your-org/backend-team
/packages/types/            @your-org/backend-team
/packages/utils/            @your-org/backend-team

# Tooling — platform team
/tooling/                   @your-org/platform

# CI configuration — platform team
/.github/                   @your-org/platform
/turbo.json                 @your-org/platform
/pnpm-workspace.yaml        @your-org/platform
```

At startup scale (2–8 engineers), "team" is often one person. That is fine. The point
is: one person is accountable, not zero people.

---

## Section 3 — Package Metadata as Machine-Readable Ownership

CODEOWNERS handles GitHub review requirements. But for programmatic tooling (Turborepo
tasks, release automation, incident routing), add ownership metadata directly to
`package.json`:

```json
{
  "name": "@your-org/database",
  "version": "1.0.0",
  "private": true,
  "x-owner": "backend-team",
  "x-tier": "shared-core",
  "x-slack-channel": "#backend"
}
```

`x-owner`, `x-tier`, and `x-slack-channel` are custom fields. They are ignored by
npm/pnpm but can be read by scripts:

```js
// tooling/scripts/list-owners.mjs
import { readFileSync } from 'fs';
import { glob } from 'glob';

const pkgs = glob.sync('**/package.json', { ignore: '**/node_modules/**' });
pkgs.forEach(p => {
  const pkg = JSON.parse(readFileSync(p, 'utf8'));
  if (pkg['x-owner']) {
    console.log(`${pkg.name} → ${pkg['x-owner']} (${pkg['x-tier']})`);
  }
});
```

Run this in CI and post the output to a Slack channel on any change to a `package.json`.

---

## Section 4 — Turborepo Pipeline Design for Cross-Team Safety

When multiple teams work in the same monorepo, Turborepo pipeline design prevents
silent breakage. The key principle: no package should be deployable without its
upstream dependencies passing tests.

Example `turbo.json`:
```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": [".next/**", "dist/**", ".wrangler/tmp/**"]
    },
    "test": {
      "dependsOn": ["^build"],
      "outputs": []
    },
    "type-check": {
      "dependsOn": ["^build"],
      "outputs": []
    },
    "deploy": {
      "dependsOn": ["build", "test", "type-check"],
      "outputs": [],
      "cache": false
    }
  }
}
```

The `^build` dependency means: build all packages that this package depends on first.
A change to `packages/database` triggers a rebuild and retest of `workers/api`
(which depends on it) automatically. Nobody needs to remember to run tests for the
downstream package.

**Filtering for per-team CI:**
```bash
# In the frontend team's PR CI job — only test what they own
pnpm turbo run test --filter=./apps/web --filter=./packages/ui

# In the backend team's PR CI job
pnpm turbo run test --filter=./workers/... --filter=./packages/database --filter=./packages/types
```

Shared packages (`packages/types`, `packages/utils`) should be tested in every PR that
touches them, regardless of which team authored the PR. Add this to the main CI job:

```bash
pnpm turbo run test --filter=...[origin/main]
```

`--filter=...[origin/main]` runs tests for every package changed relative to main,
plus all packages that depend on the changed packages.

---

## Section 5 — Shared Package Change Policy

A team working in a monorepo needs a written policy for what happens when a shared
package changes. Without it, engineers either avoid touching shared packages (the "not
my problem" freeze) or break downstream packages without noticing (the "works on my
machine" problem).

**Minimal shared package change policy:**

1. **Any change to a `packages/` package requires a `changeset`.**
   Use Changesets (`@changesets/cli`) to explicitly declare the nature of a change
   (patch, minor, major) and generate a changelog entry. This makes breaking changes
   explicit.

2. **A breaking change (major bump) requires a migration guide.**
   If `packages/database` changes a query helper signature, the PR description must
   include before/after examples and document which consumers need updating.

3. **The package owner reviews all changes to their package.**
   CODEOWNERS enforces this. Do not merge a PR that changes a shared package without
   review from the declared owner, even if the change looks trivial.

4. **Integration tests run across the dependency boundary.**
   If `packages/types` changes, the CI for `workers/api` (which consumes it) must
   pass before the PR can merge. Turborepo's `--filter=...[origin/main]` handles this.

---

## Anti-patterns

- **"Everyone owns shared packages" means nobody owns them.** Unowned packages drift:
  they accumulate undocumented behaviour, skip upgrades, and become the first place
  where security vulnerabilities linger.
- **Using the workspace root `package.json` for business logic.** The root is for
  workspace tooling only. Business logic in the root cannot be easily extracted,
  independently versioned, or independently tested.
- **Giant `packages/utils` catch-all packages.** A `utils` package that contains
  string formatting, date logic, authentication helpers, and database utilities is not
  a package — it is a junk drawer. Split by domain. Pain at split time is better than
  confusion about ownership.
- **Circular dependencies between workspace packages.** pnpm will install them but
  TypeScript and bundlers will struggle. Use `madge` to detect cycles in CI:
  `pnpm dlx madge --circular --extensions ts packages/`
- **Deploying workers without verifying their dependencies built successfully.**
  Wrangler does not run Turborepo. If you run `wrangler deploy` directly without
  first running `pnpm turbo run build`, you may deploy a Worker with a stale build of
  its shared package dependencies.

---

## Gotchas

- **pnpm workspace: protocol vs published packages.** When a Worker's `package.json`
  declares `"@your-org/database": "workspace:*"`, Wrangler must be told how to bundle
  it. Use `wrangler.toml` with `node_compat = true` and ensure the shared package is
  CommonJS or ESM compatible with the Workers runtime. Some packages using Node.js
  built-ins will not bundle cleanly.
- **`wrangler dev` does not watch workspace packages by default.** You need to run
  `pnpm turbo run build --watch --filter=@your-org/database` in parallel with
  `wrangler dev` to get hot reload of shared dependencies during local development.
- **Turborepo's remote cache requires a cache server.** Vercel's Turborepo remote
  cache is free for Vercel-hosted projects. If your CI is GitHub Actions without
  Vercel, you either pay for Turborepo Remote Cache or use a self-hosted alternative
  (Ducktape, turborepo-remote-cache on a VPS, or Cloudflare R2 as a cache backend).
- **CODEOWNERS does not prevent direct pushes to branches.** Require branch protection
  rules on `main` (require PR, require CODEOWNERS review) in GitHub settings.
  Without branch protection, CODEOWNERS is documentation, not enforcement.
- **Changeset version bumps accumulate as PRs.** If you use Changesets, the release
  PR can accumulate dozens of version bumps over a sprint. Merge it on a regular
  cadence (weekly is fine for most teams) rather than letting it grow indefinitely.

---

## Verification

A healthy pnpm workspace with explicit ownership satisfies all of these:

- [ ] Every package in `packages/` has an `x-owner` field in `package.json`
- [ ] `.github/CODEOWNERS` covers every directory under `apps/`, `workers/`,
      `packages/`, and `tooling/`
- [ ] `pnpm turbo run test --filter=...[origin/main]` passes in CI for every PR
- [ ] `pnpm dlx madge --circular --extensions ts packages/` exits with code 0
- [ ] A change to a shared package triggers test runs for all downstream consumers
- [ ] Breaking changes to shared packages include a migration guide in the PR
- [ ] Deployment scripts run `pnpm turbo run build` before `wrangler deploy`

---

## Related

- `team-topologies-organizational-design.md`
- `documentation-decays-without-ownership.md`
- `ci-matrix-rows-need-evidence-owners.md`
- `architecture-decision-records-adr-workflow.md`
- `developer-experience-dx-cloudflare-workers.md`
- `flaky-tests-destroy-ci-trust.md`

---

## Sources

- pnpm workspaces: https://pnpm.io/workspaces
- Turborepo documentation: https://turbo.build/repo/docs
- GitHub CODEOWNERS: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- Changesets: https://github.com/changesets/changesets
- Wrangler workspace packages: https://developers.cloudflare.com/workers/wrangler/configuration/
