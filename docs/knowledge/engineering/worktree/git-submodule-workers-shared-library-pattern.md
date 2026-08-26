# Git Submodule Workers Shared Library Pattern

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Three separate Cloudflare Workers repositories need to share authentication middleware,
error response helpers, and D1 query utilities. You do not want to publish a private npm
package for each utility iteration cycle. You want changes in the shared library to be
immediately consumable by downstream Workers repos without a publish step, while keeping
library versioning explicit and auditable via git history.

## Context

Git submodules embed a pointer (commit SHA) to a foreign repository inside a host repo.
For Workers monorepos that cannot or do not want to use a private npm registry, submodules
offer versioned sharing with zero registry infrastructure. The tradeoff is that downstream
repos must explicitly `git submodule update` to advance the pinned SHA. This pattern works
well for stable, slow-moving shared code (auth, middleware, schema types) but poorly for
fast-iterating application code.

---

## 1. Structure the Shared Library Repository

```
# repo: github.com/your-org/workers-shared-lib
workers-shared-lib/
  src/
    auth/
      verifyJwt.ts
      index.ts
    middleware/
      cors.ts
      rateLimit.ts
      index.ts
    db/
      userQueries.ts
      index.ts
    index.ts
  package.json      # "name": "@org/workers-shared-lib"
  tsconfig.json
  vitest.config.ts
```

```typescript
// src/auth/verifyJwt.ts
export interface JwtPayload {
  sub: string;
  email: string;
  exp: number;
}

export async function verifyJwt(
  token: string,
  secret: string
): Promise<JwtPayload> {
  // Workers-compatible JWT verification (no Node crypto)
  const [headerB64, payloadB64, sigB64] = token.split(".");
  if (!headerB64 || !payloadB64 || !sigB64) {
    throw new Response("Invalid token format", { status: 401 });
  }

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );

  const data = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const sig = Uint8Array.from(atob(sigB64.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));

  const valid = await crypto.subtle.verify("HMAC", key, sig, data);
  if (!valid) throw new Response("Invalid signature", { status: 401 });

  return JSON.parse(atob(payloadB64)) as JwtPayload;
}
```

## 2. Adding the Submodule to a Consumer Worker Repo

```bash
# Inside the consumer Worker repo
git submodule add https://github.com/your-org/workers-shared-lib.git lib/shared
git submodule update --init --recursive

# Pin to a specific release tag
git -C lib/shared checkout v1.4.2
git add lib/shared
git commit -m "chore: pin workers-shared-lib to v1.4.2"
```

After cloning the consumer repo fresh:

```bash
git clone --recurse-submodules https://github.com/your-org/consumer-worker.git
# or, if already cloned:
git submodule update --init --recursive
```

## 3. TypeScript Path Alias for the Submodule

```jsonc
// tsconfig.json (consumer Worker repo)
{
  "compilerOptions": {
    "paths": {
      "@shared/*": ["./lib/shared/src/*"]
    },
    "moduleResolution": "bundler"
  }
}
```

```typescript
// src/index.ts — consumer Worker
import { verifyJwt } from "@shared/auth";
import { corsHeaders } from "@shared/middleware/cors";
import type { Env } from "./env";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const authHeader = request.headers.get("Authorization");
    if (!authHeader?.startsWith("Bearer ")) {
      return new Response("Unauthorized", { status: 401, headers: corsHeaders });
    }

    try {
      const payload = await verifyJwt(authHeader.slice(7), env.JWT_SECRET);
      return new Response(JSON.stringify({ userId: payload.sub }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    } catch (err) {
      if (err instanceof Response) return err;
      return new Response("Internal Error", { status: 500 });
    }
  },
};
```

## 4. Wrangler Build Configuration

Wrangler uses esbuild under the hood. Because the submodule path is a local directory,
no special wrangler configuration is required — the TypeScript path alias resolves to
a relative disk path that esbuild can bundle:

```jsonc
// wrangler.jsonc
{
  "name": "consumer-api",
  "compatibility_date": "2025-11-01",
  "main": "src/index.ts",
  "build": {
    "command": "pnpm tsc --noEmit"   // type-check only; wrangler bundles via esbuild
  }
}
```

esbuild respects `tsconfig.json` `paths` during bundling when invoked via `wrangler
build`. No additional esbuild plugin is needed for local path resolution.

## 5. CI: Recursive Submodule Checkout

```yaml
# .github/workflows/ci.yml
name: CI
on: [pull_request, push]

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive      # critical — without this, lib/shared is empty
          fetch-depth: 0

      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile

      - name: Type check (includes shared lib types)
        run: pnpm tsc --noEmit

      - name: Test
        run: pnpm vitest run

      - name: Build Worker
        run: pnpm wrangler build
```

## 6. Upgrading the Shared Library Pin

```bash
# In the consumer repo
git -C lib/shared fetch --tags
git -C lib/shared checkout v1.5.0

# Review the diff between pinned versions
git -C lib/shared log v1.4.2..v1.5.0 --oneline

# If compatible, commit the new pin
git add lib/shared
git commit -m "chore(shared-lib): upgrade to v1.5.0"
```

Automate pin upgrades with Renovate by adding a `git-submodules` datasource:

```json
// renovate.json
{
  "git-submodules": { "enabled": true },
  "packageRules": [
    {
      "matchDatasources": ["git-submodules"],
      "matchPackageNames": ["lib/shared"],
      "automerge": false,
      "labels": ["shared-lib-upgrade"]
    }
  ]
}
```

---

## Anti-patterns

- **Leaving the submodule on a branch instead of a tag or commit SHA** — `git submodule
  update` will track the branch tip, making the pin non-reproducible across team members.
- **Modifying shared library source inside the consumer repo's `lib/shared` directory** —
  changes are silently lost on the next `git submodule update` unless pushed to the shared
  library repo first.
- **Skipping `submodules: recursive` in CI** — the submodule directory is empty (an empty
  placeholder), wrangler build succeeds but bundles nothing from `@shared/*` paths,
  producing a broken Worker with no compile error.
- **Using submodules for rapidly-changing code** — every change requires: commit in
  shared lib → push → update pin in consumer → PR. A private npm package or pnpm
  workspace is lower-friction for fast-moving code.

## Gotchas

- `git clone --recurse-submodules` checks out the SHA pinned in `.gitmodules`, not the
  current `HEAD` of the shared library. This is the desired behaviour, but surprises
  developers expecting the latest version.
- esbuild (via wrangler) does NOT read `tsconfig.json` `paths` for module resolution
  unless `tsconfig.json` is in the project root and `moduleResolution` is set to
  `bundler` or `node`. Using `node16` resolution with paths requires an explicit esbuild
  plugin.
- Renovate's `git-submodules` support requires the Renovate bot to have read access to
  the shared library repo. Private repos need an explicit token in the Renovate config.
- Forked repos do not carry submodule content by default. Contributors must run `git
  submodule update --init` after forking.

## Verification

```bash
# Confirm submodule is checked out and at expected SHA
git submodule status
# => abc1234 lib/shared (v1.4.2)

# Confirm type alias resolves
pnpm tsc --noEmit
# => no errors

# Confirm bundle includes shared code
pnpm wrangler build --dry-run 2>&1 | grep "verifyJwt\|corsHeaders"
# => should show paths in bundle output
```

## Related

- `git-submodule-vs-pnpm-workspace-workers-packages.md`
- `git-submodules-subtrees-2026.md`
- `monorepo-workspace-cloudflare-workers.md`
- `typescript-path-aliases-monorepo-workers-build.md`
- `dependency-update-automation-renovate.md`

## Sources

- git-submodule(1) man page
- esbuild path aliasing — esbuild.github.io/api/#alias
- Renovate git-submodules support — docs.renovatebot.com/modules/datasource/git-submodules
- Cloudflare Workers esbuild bundler docs (2025)
