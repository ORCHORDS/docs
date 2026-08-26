# GitHub Codespaces Devcontainer with D1 and R2 Local Emulation

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Developers on a Workers project using D1 and R2 want a cloud development environment that starts in seconds and
already has Wrangler's local emulators configured, migrations applied, and R2 bucket seeds loaded — without
requiring any local tooling or manual setup steps. Opening the repository in GitHub Codespaces should yield a
fully functional dev environment with `wrangler dev --local` working out of the box.

## Context

Wrangler 3+ ships `--local` mode for both D1 (via `better-sqlite3`) and R2 (via a local filesystem shard).
GitHub Codespaces devcontainers support `postCreateCommand` and `postStartCommand` lifecycle hooks that run
arbitrary scripts inside the container. Combining a curated `devcontainer.json`, a Dockerfile (or a base
Microsoft image), and lifecycle scripts produces a zero-friction onboarding experience that mirrors a CI-verified
local state. Port forwarding is configured so the Worker preview is accessible directly in the browser.

---

## Devcontainer Base Configuration

```json
// .devcontainer/devcontainer.json
{
  "name": "Workers + D1 + R2 Dev",
  "image": "mcr.microsoft.com/devcontainers/typescript-node:22-bookworm",
  "features": {
    "ghcr.io/devcontainers/features/github-cli:1": {}
  },
  "forwardPorts": [8787, 8788],
  "portsAttributes": {
    "8787": { "label": "Wrangler Dev", "onAutoForward": "openBrowser" },
    "8788": { "label": "Wrangler Inspector" }
  },
  "postCreateCommand": "bash .devcontainer/setup.sh",
  "postStartCommand": "bash .devcontainer/start-dev.sh",
  "customizations": {
    "vscode": {
      "extensions": [
        "cloudflare.cloudflare-workers-bindings",
        "dbaeumer.vscode-eslint",
        "esbenp.prettier-vscode"
      ],
      "settings": {
        "editor.formatOnSave": true,
        "editor.defaultFormatter": "esbenp.prettier-vscode"
      }
    }
  },
  "remoteEnv": {
    "WRANGLER_LOG": "debug",
    "MINIFLARE_WORKERS_CONFIGS": ".wrangler/state"
  }
}
```

---

## Setup Script: Dependencies, Migrations, and Seed Data

```bash
#!/usr/bin/env bash
# .devcontainer/setup.sh — runs once on container creation
set -euo pipefail

echo "==> Installing dependencies"
npm ci

echo "==> Creating local D1 database and running migrations"
# Wrangler local D1 lives in .wrangler/state/v3/d1/
npx wrangler d1 migrations apply DB --local

echo "==> Seeding D1 with development fixtures"
if [ -f "db/seed.sql" ]; then
  npx wrangler d1 execute DB --local --file=db/seed.sql
fi

echo "==> Initialising local R2 bucket directories"
# Wrangler local R2 stores objects at .wrangler/state/v3/r2/<bucket>/
mkdir -p .wrangler/state/v3/r2/ASSETS
if [ -d "fixtures/r2" ]; then
  cp -r fixtures/r2/. .wrangler/state/v3/r2/ASSETS/
fi

echo "==> Codespace setup complete"
```

---

## Start Script: Launching Wrangler Dev in Background

```bash
#!/usr/bin/env bash
# .devcontainer/start-dev.sh — runs on every container start/restart
set -euo pipefail

# Kill any stale wrangler process from a previous session
pkill -f "wrangler dev" 2>/dev/null || true

echo "==> Starting Wrangler dev (local D1 + R2)"
nohup npx wrangler dev \
  --local \
  --port 8787 \
  --inspector-port 8788 \
  --ip 0.0.0.0 \
  > /tmp/wrangler-dev.log 2>&1 &

echo "Wrangler PID: $!"
echo "Logs: tail -f /tmp/wrangler-dev.log"
```

---

## Wrangler Configuration for Local Emulation

Ensure `wrangler.toml` declares the local-compatible bindings. Secrets for local use go in `.dev.vars`
(gitignored) rather than Codespaces secrets so no manual secret injection is required.

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id = "REMOTE_DB_UUID"    # used only for --remote; --local ignores this

[[r2_buckets]]
binding = "ASSETS"
bucket_name = "my-assets"         # --local uses .wrangler/state/v3/r2/ASSETS/
```

```bash
# .dev.vars  (gitignored — checked in as .dev.vars.example)
API_SECRET=local-dev-secret
ENVIRONMENT=development
```

---

## Accessing the Local Worker from the Codespace Browser

Codespaces automatically forwards port 8787 with HTTPS via the `CODESPACE_NAME` subdomain. Workers code
that checks `request.url` for HTTPS will work correctly because Codespaces terminates TLS at the proxy layer.

```typescript
// src/index.ts — environment detection helper
export function isLocalDev(env: Env): boolean {
  return env.ENVIRONMENT === "development";
}

// Use local-safe values when running in Codespaces
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const origin = isLocalDev(env)
      ? `https://${process.env.CODESPACE_NAME}-8787.app.github.dev`
      : "https://my-worker.workers.dev";

    // ... handler logic
    return new Response(`Running at ${origin}`);
  },
};
```

---

## Prebuilding the Devcontainer for Faster Starts

Add a prebuild configuration so Codespaces pre-runs `postCreateCommand` on every push to `main`, cutting cold
start time from ~3 minutes to under 30 seconds.

```json
// .devcontainer/devcontainer.json  (add inside the root object)
"build": {
  "dockerfile": "Dockerfile"
},
"initializeCommand": "echo 'Prebuild: $(date)'"
```

```yaml
# .github/workflows/devcontainer-prebuild.yml
name: Devcontainer Prebuild

on:
  push:
    branches: [main]
    paths:
      - ".devcontainer/**"
      - "package*.json"
      - "db/migrations/**"

jobs:
  prebuild:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - name: Trigger Codespaces prebuild
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh api \
            --method POST \
            -H "Accept: application/vnd.github+json" \
            "/repos/${{ github.repository }}/codespaces/prebuilds" \
            -f ref="main" \
            -f location="EastUs"
```

---

## Anti-patterns

- **Committing `.wrangler/state/`** — the local D1 SQLite file and R2 shard contain developer-specific state and
  binary data. Always add `.wrangler/` to `.gitignore`.
- **Using `--remote` in Codespaces** — `wrangler dev --remote` routes traffic to production infrastructure,
  which burns D1/R2 billing units and can corrupt real data during development. Use `--local` in Codespaces.
- **Storing real secrets in `.dev.vars`** — `.dev.vars` is gitignored but Codespaces secrets (set via
  `gh codespace secrets set`) are the correct mechanism for shared credentials needed in dev. Use `.dev.vars`
  only for non-sensitive local-only overrides.
- **Running `wrangler dev` in `postCreateCommand`** — it must run in `postStartCommand` so it restarts when
  the Codespace is stopped and resumed.

---

## Gotchas

- Wrangler's local D1 uses `better-sqlite3` under the hood, which requires native binaries. The
  `mcr.microsoft.com/devcontainers/typescript-node` image ships glibc 2.35 (Debian bookworm) which is
  compatible; Alpine-based images require additional `libc6-compat` layers.
- Port `8787` must be explicitly opened to `0.0.0.0` with `--ip 0.0.0.0`; the default `127.0.0.1` is not
  reachable from the Codespaces browser proxy.
- Local R2 does not enforce bucket-level CORS or lifecycle rules; tests that rely on these behaviors must
  run against a staging bucket with `--remote`.
- Codespaces prebuilds expire after **30 days** by default; configure the retention policy in
  Organization Settings → Codespaces to avoid falling back to cold starts.

---

## Verification

```bash
# Inside the Codespace terminal
tail -f /tmp/wrangler-dev.log

# Confirm D1 local tables are seeded
npx wrangler d1 execute DB --local --command "SELECT name FROM sqlite_master WHERE type='table';"

# Confirm R2 local bucket is populated
ls .wrangler/state/v3/r2/ASSETS/

# Hit the Worker
curl http://localhost:8787/healthz
```

---

## Related

- `github-codespaces-cloudflare-workers-dev-environment.md`
- `github-codespaces-devcontainer.md`
- `github-codespaces-prebuild-freshness-and-cost-policy.md`
- `github-actions-cloudflare-d1-migration-pipeline.md`

---

## Sources

- https://developers.cloudflare.com/workers/local-development/
- https://developers.cloudflare.com/d1/local-development/
- https://developers.cloudflare.com/r2/local-development/
- https://docs.github.com/en/codespaces/setting-up-your-project-for-codespaces/adding-a-dev-container-configuration
- https://docs.github.com/en/codespaces/prebuilding-your-codespaces/about-github-codespaces-prebuilds
