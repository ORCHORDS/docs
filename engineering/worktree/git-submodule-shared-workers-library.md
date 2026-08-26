# Git Submodule — Shared Workers Utilities Library

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You maintain a shared `workers-utils` library consumed by multiple independent Cloudflare Workers repositories. You want all consumers to reference a pinned, auditable version of the library without publishing it to npm, and you want CI to always build against the pinned commit.

---

## Context

Git submodules embed one repository inside another at a specific commit SHA. The parent repo tracks the submodule path and the pinned commit; the submodule itself is a fully independent git repo. This is ideal for a shared Workers utilities library because the library can be developed and versioned separately while each consumer explicitly opts into new versions via `git submodule update --remote`. Wrangler supports referencing external modules by path, so a submodule in `./vendor/workers-utils/src` is directly importable at build time. CI pipelines must use `--recurse-submodules` on checkout to populate the submodule content.

---

## Section 1 — Adding and Pinning the Submodule

```bash
# In the consumer repository root
git submodule add https://github.com/example-org/example-repo vendor/workers-utils

# This creates:
# .gitmodules          — records the submodule URL and path
# vendor/workers-utils — the checked-out submodule at HEAD of default branch

# Pin the submodule to a specific commit (e.g. a stable release tag)
cd vendor/workers-utils
git checkout v1.4.2       # or a specific SHA
cd ../..
git add vendor/workers-utils
git commit -m "chore(deps): pin workers-utils to v1.4.2"

# Verify the pinned state
git submodule status
# abc1234 vendor/workers-utils (v1.4.2)

# .gitmodules contents after add
cat .gitmodules
# [submodule "vendor/workers-utils"]
#   path = vendor/workers-utils
#   url = https://github.com/example-org/example-repo
#   branch = main
```

```toml
# wrangler.toml — referencing the submodule path
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"
node_compat = true

# Tell Wrangler where to find external modules from the submodule
# When using tsc/esbuild, the tsconfig paths handle resolution at build time.
# The submodule source is available at vendor/workers-utils/src.
```

```json
// tsconfig.json — path aliases for the submodule
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "paths": {
      "@workers-utils/*": ["./vendor/workers-utils/src/*"]
    }
  },
  "include": ["src/**/*", "vendor/workers-utils/src/**/*"]
}
```

---

## Section 2 — Importing and Using the Library

```typescript
// vendor/workers-utils/src/cors.ts (the shared library)
export interface CorsOptions {
  allowedOrigins: string[];
  allowedMethods?: string[];
  allowCredentials?: boolean;
}

export function withCors(response: Response, options: CorsOptions): Response {
  const headers = new Headers(response.headers);
  headers.set('Access-Control-Allow-Origin', options.allowedOrigins.join(', '));
  headers.set(
    'Access-Control-Allow-Methods',
    (options.allowedMethods ?? ['GET', 'POST', 'OPTIONS']).join(', ')
  );
  if (options.allowCredentials) {
    headers.set('Access-Control-Allow-Credentials', 'true');
  }
  return new Response(response.body, { ...response, headers });
}

export function handlePreflight(request: Request): Response | null {
  if (request.method === 'OPTIONS') {
    return new Response(null, { status: 204 });
  }
  return null;
}
```

```typescript
// src/index.ts — consumer Worker importing from the submodule
import { withCors, handlePreflight } from '@workers-utils/cors';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const preflight = handlePreflight(request);
    if (preflight) return preflight;

    const response = await handleRequest(request, env);
    return withCors(response, {
      allowedOrigins: ['https://app.example.com'],
      allowedMethods: ['GET', 'POST'],
      allowCredentials: true,
    });
  },
};

async function handleRequest(request: Request, env: Env): Promise<Response> {
  return new Response('Hello from Worker', { status: 200 });
}

interface Env {
  API_KEY: string;
}
```

---

## Section 3 — Updating Consumers and CI Checkout

```bash
# Update submodule to the latest commit on its tracked branch
git submodule update --remote vendor/workers-utils
git add vendor/workers-utils
git commit -m "chore(deps): update workers-utils to latest main"

# Update to a specific new tag
cd vendor/workers-utils && git checkout v1.5.0 && cd ../..
git add vendor/workers-utils
git commit -m "chore(deps): upgrade workers-utils to v1.5.0"
git push origin main

# Initialize and update submodules after a fresh clone
git clone --recurse-submodules https://github.com/example-org/example-repo
# OR for an existing clone that wasn't initialized
git submodule update --init --recursive
```

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}

    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive   # Populates vendor/workers-utils at the pinned SHA
          fetch-depth: 0

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - name: Install dependencies
        run: npm ci

      - name: Typecheck
        run: npx tsc --noEmit

      - name: Build
        run: npm run build

      - name: Deploy
        if: github.ref == 'refs/heads/main'
        run: npx wrangler deploy

      - name: Verify deployment
        if: github.ref == 'refs/heads/main'
        run: |
          sleep 5
          curl --fail https://my-worker.example.com/health
```

---

## Anti-patterns

- **Checking out the submodule on a branch instead of a tag/SHA** — If the submodule is on a branch (`main`), `git submodule update` may pull in new commits without an explicit upgrade commit in the parent repo. Always pin to a tag or SHA for reproducibility.
- **Importing the submodule with an absolute path in wrangler.toml** — Absolute paths break in CI. Use tsconfig `paths` or relative imports relative to the project root.
- **Omitting `submodules: recursive` in CI checkout** — Without this flag, `vendor/workers-utils` will be an empty directory and the build will fail with missing module errors.
- **Editing files inside `vendor/workers-utils` directly in the consumer repo** — Changes in the submodule directory are local to your machine and will be lost on the next `submodule update`. Contribute changes back to the library repo instead.
- **Using `https` submodule URLs in repos that require SSH for CI** — If your CI authenticates via SSH deploy keys, ensure `.gitmodules` uses the correct protocol that CI credentials support, or configure `url.<base>.insteadOf` in git config.

---

## Gotchas

- `git clone` without `--recurse-submodules` leaves `vendor/workers-utils` as an empty directory — always remind contributors to run `git submodule update --init --recursive` after cloning.
- `git pull` on the parent repo does NOT automatically update submodule contents — run `git submodule update --recursive` after pulling if the pinned commit changed.
- Forking a repo with submodules on GitHub does not fork the submodule — the fork still points to the original submodule URL.
- `git diff` in the parent repo shows submodule changes as a single commit SHA diff, not file-level diffs. Use `git diff --submodule=diff` for file-level detail.
- Private submodule repos require that CI has read access (deploy key or GitHub App) to the submodule repository separately from the parent repo.

---

## Verification

```bash
# Confirm submodule is initialized and at the pinned commit
git submodule status
# Should show: abc1234 vendor/workers-utils (v1.4.2)

# Confirm TypeScript resolves the path alias
npx tsc --noEmit 2>&1 | grep -i error
# Should produce no output

# Confirm the build output includes the submodule code
npm run build && ls -lh dist/

# Test locally with wrangler
npx wrangler dev --port 8787 --local
curl http://localhost:8787/health
```

---

## Related

- `git-worktree-parallel-feature-development.md`
- `git-worktree-release-branch-cherry-pick.md`

---

## Sources

- Git Submodules Documentation — https://git-scm.com/book/en/v2/Git-Tools-Submodules
- GitHub Actions Checkout — Submodules — https://github.com/actions/checkout#submodules
- Wrangler External Modules — https://developers.cloudflare.com/workers/wrangler/configuration/#bundling
