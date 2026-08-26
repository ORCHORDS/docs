# code-organization-monorepo

**Issue:** Monorepo vs polyrepo, when to use which
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have 3 apps: web, mobile, backend. Each is a separate
repo. A change to the API breaks the web app. The web
app is in a separate repo; you can't easily test the
integration. You wish you had one repo.

## Root cause
**Polyrepos are great for separation, terrible for
collaboration.** Monorepos are great for collaboration,
harder for separation.

**Source:** Various monorepo guides.

## The "monorepo vs polyrepo" decision

### Monorepo (one repo, multiple packages)
- **Pros:**
  - Shared code is easy (TypeScript types, components)
  - Atomic changes across packages
  - Single CI/CD pipeline
  - Single source of truth
- **Cons:**
  - More complex tooling
  - Larger clone size
  - Tighter coupling (can import anything)

### Polyrepo (one repo per app)
- **Pros:**
  - Clear boundaries
  - Smaller, focused repos
  - Independent deploys
  - Different teams own different repos
- **Cons:**
  - Shared code is hard (copy-paste or packages)
  - Cross-repo changes are hard (multiple PRs)
  - Integration testing is hard

For most teams, **monorepo** is the right answer for small-
to-medium teams (1-20). For very large teams (100+),
polyrepo may be better.

## The "monorepo tools"

| Tool | Lang | Notes |
|---|---|---|
| **pnpm workspaces** | JS/TS | Fast, simple |
| **npm workspaces** | JS/TS | Built into npm |
| **yarn workspaces** | JS/TS | Mature, plugins |
| **Nx** | JS/TS | Full-featured, caching |
| **Turborepo** | JS/TS | Fast, simple |
| **Bazel** | Multi-lang | Powerful, complex |
| **Lerna** | JS/TS | Older, declining |

For most JS/TS projects, **pnpm workspaces + Turborepo** is
the right combination.

## The "pnpm workspaces" pattern

```json
// pnpm-workspace.yaml
packages:
  - "apps/*"
  - "packages/*"
```

```
my-monorepo/
├── apps/
│   ├── web/         # Next.js app
│   ├── api/         # Cloudflare Worker
│   └── admin/       # Internal tool
├── packages/
│   ├── ui/          # Shared components
│   ├── types/       # Shared TypeScript types
│   ├── db/          # D1 schema + migrations
│   └── utils/       # Shared utilities
├── package.json
├── pnpm-workspace.yaml
└── turbo.json
```

## The "shared code" pattern

For shared code, use a package:
```ts
// packages/types/src/user.ts
export interface User {
  id: string;
  email: string;
  displayName: string;
  role: 'viewer' | 'admin' | 'owner';
}
```

```json
// apps/web/package.json
{
  "dependencies": {
    "@myorg/types": "workspace:*"
  }
}
```

The web app imports the types from the shared package.

## The "build orchestration" pattern

For a monorepo, use Turborepo:
```json
// turbo.json
{
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**"]
    },
    "test": {
      "dependsOn": ["^build"]
    },
    "lint": {},
    "deploy": {
      "dependsOn": ["build", "test", "lint"]
    }
  }
}
```

The build is cached; only changed packages are rebuilt.

## The "versioning" pattern

For monorepo versioning, options:
- **Fixed:** All packages have the same version (e.g.
  React's monorepo)
- **Independent:** Each package has its own version
  (e.g. most monorepos)
- **Hybrid:** Some packages fixed, some independent

For most apps, **independent** is the right answer.

## The "changesets" pattern

For versioned changes, use changesets:
```bash
pnpm changeset
# Creates a markdown file describing the change
```

```markdown
// .changeset/abc-123.md
---
'@myorg/types': minor
'@myorg/web': patch
---

Add a new `role` field to the User type.
```

```bash
pnpm changeset version
# Updates package.json files

pnpm changeset publish
# Publishes to npm
```

## The "code sharing" rules

For a monorepo, the rules:
- **Apps can import from packages** ✅
- **Packages can import from other packages** ✅
- **Packages cannot import from apps** ❌
- **Apps cannot import from other apps** ❌

Enforce with ESLint:
```json
// .eslintrc.json
{
  "rules": {
    "import/no-restricted-paths": ["error", {
      "zones": [
        { "target": "./apps/*", "from": "./apps/*", "message": "Apps cannot import from other apps" },
        { "target": "./packages/*", "from": "./apps/*", "message": "Packages cannot import from apps" }
      ]
    }]
  }
}
```

The rules prevent accidental coupling.

## The "CI" pattern

For monorepo CI, use Turborepo's `--filter`:
```yaml
# .github/workflows/ci.yml
- name: Build
  run: pnpm turbo build --filter=[origin/main]
  # Only build packages changed since main
```

The CI is fast; only changed packages are built.

## The "deploy" pattern

For deploys, each app deploys independently:
```yaml
- name: Deploy API
  if: contains(github.event.head_commit.modified, 'apps/api/')
  run: cd apps/api && wrangler deploy

- name: Deploy Web
  if: contains(github.event.head_commit.modified, 'apps/web/')
  run: cd apps/web && vercel deploy
```

Only the changed apps are deployed.

## The "dependency hoisting" pattern

For pnpm, dependencies are hoisted to the workspace root:
```
my-monorepo/
├── node_modules/        # Hoisted deps
├── apps/
│   └── web/
│       └── node_modules/  # Local deps only
```

This saves disk + speeds up installs.

## The "monorepo" anti-patterns

### 1. Apps importing from apps
- **Symptom:** The web app imports the admin app
- **Fix:** Move the shared code to a package

### 2. Packages with too much code
- **Symptom:** A package is huge; every change to the
  package breaks every app
- **Fix:** Split the package; smaller, focused packages

### 3. No versioning
- **Symptom:** All packages are at "latest" forever
- **Fix:** Use changesets

### 4. No CI optimization
- **Symptom:** A change to one package rebuilds everything
- **Fix:** Use Turborepo; cache the build

### 5. Tight coupling
- **Symptom:** A change to a package requires changes to
  10 apps
- **Fix:** Smaller, focused packages with clear APIs

## The "monorepo migration" pattern

For migrating from polyrepo to monorepo:
1. **Inventory the repos**
2. **Identify shared code** (packages)
3. **Create the monorepo structure**
4. **Move the repos in** (git history preserved)
5. **Update the imports**
6. **Set up the CI**

The migration is a project (weeks). Plan accordingly.

## Verification
- **Test:** The monorepo builds + tests + deploys
- **Live:** CI is fast (Turborepo caching works)
- **Audit:** Quarterly review of the monorepo

## Gotchas
- **The "monorepo is a silver bullet" anti-pattern.** A
  monorepo doesn't fix bad architecture. It just makes
  bad architecture easier.
- **The "everything in one package" anti-pattern.** Don't
  put everything in one package. Use focused packages.
- **The "no boundaries" anti-pattern.** Without ESLint
  rules, the monorepo becomes a big ball of mud.
- **The "monorepo grows forever" anti-pattern.** A
  monorepo with 100 packages is unmanageable. Move some
  out.
- **The "no caching" anti-pattern.** Without Turborepo, the
  CI is slow. Use caching.

## Related
- `infra/pnpm-workspaces-monorepo.md`
- `code-organization.md` (later)
- `safe-deploy-checklist.md`
- Turborepo: https://turbo.build/
- pnpm: https://pnpm.io/
- Nx: https://nx.dev/
- Changesets: https://github.com/changesets/changesets
