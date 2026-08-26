# git describe Version Strings in Cloudflare Workers CI

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your Cloudflare Workers deployment has no human-readable version embedded in it. When a bug surfaces in production you cannot tell which exact commit or tag is running without querying Wrangler or cross-referencing SHA hashes in GitHub Actions logs. You want a version string like `v1.4.2-3-gabcdef1` automatically injected at build time so every Worker can surface its own version through a `/version` endpoint or a `Cf-Worker-Version` response header.

## Context

`git describe` traverses the commit ancestry to find the nearest annotated tag, then appends the number of commits since that tag and a short object hash. The result is a compact, human-readable, semver-compatible string that pinpoints a build exactly. In Cloudflare Workers CI pipelines this string is the cheapest possible audit trail: it costs zero storage, is embedded at build time via `wrangler.toml` vars or `define` substitution, and is queryable at runtime without external lookups.

Wrangler supports injecting arbitrary strings into Worker bundles through `[vars]` in `wrangler.toml`, environment-level overrides, or the `--var` CLI flag. Combined with `git describe`, this produces reproducible version metadata with no extra infrastructure.

---

## Generating the Version String in CI

The canonical command for a clean, tag-annotated repository:

```bash
git describe --tags --always --dirty=-dirty
```

- `--tags` falls back to lightweight tags if no annotated tag exists.
- `--always` falls back to the short SHA when no tag exists at all.
- `--dirty=-dirty` appends the suffix when the working tree has uncommitted changes (useful to catch accidental deploys of locally modified code).

In GitHub Actions:

```yaml
# .github/workflows/deploy.yml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0          # required — shallow clones break git describe

      - name: Compute version
        id: version
        run: |
          VERSION=$(git describe --tags --always --dirty=-dirty)
          echo "VERSION=$VERSION" >> "$GITHUB_OUTPUT"

      - name: Deploy Worker
        run: |
          npx wrangler deploy \
            --var WORKER_VERSION:"${{ steps.version.outputs.VERSION }}"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## Exposing the Version at Runtime

Declare the variable in `wrangler.toml` with a placeholder that CI overrides:

```toml
# wrangler.toml
name = "my-api"
compatibility_date = "2026-01-01"

[vars]
WORKER_VERSION = "dev"
```

Consume it in the Worker:

```typescript
// src/index.ts
export interface Env {
  WORKER_VERSION: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/version") {
      return Response.json({ version: env.WORKER_VERSION });
    }

    const response = await handleRequest(request, env);

    // Attach version to every response for easy curl inspection
    const headers = new Headers(response.headers);
    headers.set("X-Worker-Version", env.WORKER_VERSION);
    return new Response(response.body, { status: response.status, headers });
  },
};
```

---

## Blocking Deploys on Dirty Working Trees

Add a pre-deploy gate in CI to prevent deploying dirty builds:

```bash
#!/usr/bin/env bash
# scripts/assert-clean-deploy.sh
set -euo pipefail

VERSION=$(git describe --tags --always --dirty=-dirty)

if [[ "$VERSION" == *"-dirty" ]]; then
  echo "ERROR: working tree is dirty. Refusing deploy." >&2
  echo "Run 'git status' to inspect uncommitted changes." >&2
  exit 1
fi

echo "Clean build: $VERSION"
```

Call it as a step before `wrangler deploy`:

```yaml
- name: Assert clean build
  run: bash scripts/assert-clean-deploy.sh
```

---

## Monorepo: Per-Package Version Strings

In a monorepo with multiple Workers, scope the tag search to package-level tags:

```bash
# Tag convention: <package>@<semver>
# e.g. api-gateway@1.2.0, auth-worker@3.0.1

PACKAGE="api-gateway"
VERSION=$(git describe --tags --always --match "${PACKAGE}@*" \
            --abbrev=7 --dirty=-dirty)
echo "$VERSION"
# api-gateway@1.2.0-4-gabcdef1
```

Wire this into a Turborepo pipeline task:

```json
// turbo.json (excerpt)
{
  "tasks": {
    "deploy": {
      "dependsOn": ["build"],
      "env": ["CLOUDFLARE_API_TOKEN"],
      "outputs": []
    }
  }
}
```

```bash
# packages/api-gateway/package.json scripts
"deploy": "VERSION=$(git describe --tags --always --match 'api-gateway@*' --dirty=-dirty) npx wrangler deploy --var WORKER_VERSION:\"$VERSION\""
```

---

## Surfacing Version in Tail Workers Logs

Attach the version to every log event so Tail Workers can filter by release:

```typescript
// src/logger.ts
export function createLogger(env: Env, ctx: ExecutionContext) {
  return {
    info(message: string, data?: Record<string, unknown>) {
      console.log(
        JSON.stringify({
          level: "info",
          message,
          version: env.WORKER_VERSION,
          timestamp: new Date().toISOString(),
          ...data,
        })
      );
    },
  };
}
```

---

## Anti-patterns

- **Shallow clone without `fetch-depth: 0`**: `actions/checkout` defaults to a depth-1 clone. `git describe` cannot traverse history and returns bare SHAs or fails entirely. Always set `fetch-depth: 0` on deploy jobs.
- **Using `GITHUB_SHA` instead of `git describe`**: `GITHUB_SHA` is a full 40-character hash with no tag context. It tells you nothing about the distance from the last release.
- **Hardcoding the version in `wrangler.toml`**: The `[vars]` placeholder is only a default; CI must always override it. If the CI step is skipped silently, the deployed Worker reads `"dev"` in production with no warning.
- **Lightweight tags instead of annotated tags**: `git describe` requires annotated tags by default (`git tag -a v1.0.0 -m "release"`). Lightweight tags need `--tags` flag and produce less reliable results in busy repositories.

---

## Gotchas

- `--dirty` detection runs against the index, not just tracked files. Untracked files in the working directory do not trigger the dirty flag; only staged or unstaged changes to tracked files do.
- In GitHub Actions the `GITHUB_OUTPUT` mechanism replaced `set-output` in 2022. Use `echo "KEY=VALUE" >> "$GITHUB_OUTPUT"` not `::set-output::`.
- If no tag exists anywhere in history, `git describe --always` returns the short SHA (7 chars by default). The `--abbrev=N` flag controls length.
- Wrangler's `--var KEY:VALUE` syntax uses a colon separator, not `=`. Using `=` silently produces a malformed variable name.

---

## Verification

```bash
# Confirm git describe output locally
git describe --tags --always --dirty=-dirty

# Deploy to staging and verify header
curl -si https://my-api.workers.dev/version | jq .

# Expected output
# {"version":"v1.4.2-3-gabcdef1"}

# Confirm header on any endpoint
curl -si https://my-api.workers.dev/ | grep X-Worker-Version
```

---

## Related

- `git-tag-semantic-versioning-workers-deploy-gates.md`
- `github-actions-wrangler-deploy-pipeline.md`
- `wrangler-environments-staging-production.md`
- `cloudflare-workers-observability-tail-workers.md`
- `monorepo-wrangler-selective-deploy.md`

---

## Sources

- git-scm.com/docs/git-describe
- developers.cloudflare.com/workers/wrangler/commands/#deploy
- docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions
- developers.cloudflare.com/workers/configuration/environment-variables/
