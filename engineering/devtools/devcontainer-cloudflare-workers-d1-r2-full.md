# Full Devcontainer for Cloudflare Workers with D1/R2/KV

- Date: 2026-08-22
- Author: example.com
- Status: production

## Consistent Local Workers Development Across Machines

Cloudflare Workers local development has more moving parts than a typical Node.js project: Wrangler 4, the correct Node.js version, pnpm, D1 SQLite state, R2 object storage, KV persistence, and `wrangler dev` port forwarding. Getting all of this working identically on a new developer's machine or in a GitHub Codespace used to take an afternoon. A devcontainer definition encodes the full environment declaratively, so cloning the repo and opening in VS Code or Codespace is sufficient to start hacking.

This article documents a complete `.devcontainer/devcontainer.json` configuration that installs Wrangler, pre-configures local D1/R2/KV bindings, forwards the correct ports, installs useful VS Code extensions, and runs a post-create script that seeds the local database. The setup is tested on both macOS (OrbStack) and GitHub Codespaces.

The key constraint driving several decisions: Wrangler's local persistence directories must live inside the container's workspace mount, not in a platform-specific location, so they survive container rebuilds via a named volume.

## Context

- Base image: `mcr.microsoft.com/devcontainers/typescript-node:22`
- Package manager: pnpm 9 (via Corepack)
- Workers tooling: Wrangler 4.x
- Local bindings: D1 (SQLite), R2 (disk), KV (disk)
- Port: 8787 (`wrangler dev` default)
- VS Code extensions: Cloudflare Workers, ESLint, Biome, GitLens

## devcontainer.json

```json
{
  "name": "Cloudflare Workers Dev",
  "image": "mcr.microsoft.com/devcontainers/typescript-node:1-22-bookworm",

  "features": {
    "ghcr.io/devcontainers/features/common-utils:2": {
      "installZsh": true,
      "configureZshAsDefaultShell": true,
      "installOhMyZsh": true,
      "upgradePackages": true
    },
    "ghcr.io/devcontainers/features/git:1": {
      "ppa": true,
      "version": "latest"
    },
    "ghcr.io/devcontainers/features/docker-in-docker:2": {
      "version": "latest",
      "dockerDashComposeVersion": "v2"
    }
  },

  "mounts": [
    {
      "source": "workers-local-persistence",
      "target": "${containerWorkspaceFolder}/.wrangler",
      "type": "volume"
    }
  ],

  "forwardPorts": [8787, 8788, 9229],
  "portsAttributes": {
    "8787": {
      "label": "wrangler dev (primary Worker)",
      "onAutoForward": "notify"
    },
    "8788": {
      "label": "wrangler dev (secondary Worker / D1 HTTP)",
      "onAutoForward": "silent"
    },
    "9229": {
      "label": "Node.js inspector / wrangler debug",
      "onAutoForward": "silent"
    }
  },

  "customizations": {
    "vscode": {
      "extensions": [
        "cloudflare.cloudflare-workers-bindings-extension",
        "biomejs.biome",
        "dbaeumer.vscode-eslint",
        "eamodio.gitlens",
        "ms-vscode.vscode-typescript-next",
        "bradlc.vscode-tailwindcss",
        "ms-azuretools.vscode-docker",
        "EditorConfig.EditorConfig",
        "streetsidesoftware.code-spell-checker"
      ],
      "settings": {
        "terminal.integrated.defaultProfile.linux": "zsh",
        "editor.formatOnSave": true,
        "editor.defaultFormatter": "biomejs.biome",
        "[typescript]": {
          "editor.defaultFormatter": "biomejs.biome"
        },
        "typescript.tsdk": "node_modules/typescript/lib",
        "eslint.useFlatConfig": true,
        "eslint.experimental.useFlatConfig": true
      }
    }
  },

  "postCreateCommand": ".devcontainer/post-create.sh",
  "postStartCommand": ".devcontainer/post-start.sh",

  "remoteEnv": {
    "WRANGLER_LOG": "debug",
    "CLOUDFLARE_API_TOKEN": "${localEnv:CLOUDFLARE_API_TOKEN}",
    "MINIFLARE_WORKERS_CONFIGS": "${containerWorkspaceFolder}/wrangler.toml"
  },

  "containerEnv": {
    "COREPACK_ENABLE_AUTO_PIN": "0"
  }
}
```

## Post-Create Script

`.devcontainer/post-create.sh` runs once after the container is created:

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "==> Enabling Corepack and installing pnpm"
corepack enable
corepack prepare pnpm@9 --activate

echo "==> Installing workspace dependencies"
pnpm install

echo "==> Generating wrangler types"
pnpm --filter "./apps/*" run types 2>/dev/null || true

echo "==> Creating local D1 database"
# wrangler will create the .wrangler/state/v3/d1 directory automatically
# on first access; run a migration to seed the schema
pnpm --filter api exec wrangler d1 migrations apply DB --local

echo "==> Seeding D1 with development data"
pnpm --filter api exec wrangler d1 execute DB --local \
  --file=./db/seeds/dev.sql

echo "==> Verifying local KV namespace"
pnpm --filter api exec wrangler kv key put \
  --binding=CACHE "health-check" "ok" --local 2>/dev/null || true

echo "==> Verifying local R2 bucket"
# Create a marker object so the bucket directory is initialized
echo "devcontainer-ready" | pnpm --filter api exec wrangler r2 object put \
  ASSETS/.devcontainer-ready --pipe --local 2>/dev/null || true

echo ""
echo "==> Dev environment ready. Run: pnpm --filter api run dev"
```

## Post-Start Script

`.devcontainer/post-start.sh` runs every time the container starts (including after rebuilds):

```bash
#!/usr/bin/env bash
set -euo pipefail

# Restore pnpm symlinks if volume was remounted without node_modules
if [ ! -d "node_modules/.pnpm" ]; then
  echo "==> Restoring node_modules after volume remount"
  pnpm install --frozen-lockfile
fi

# Apply any pending D1 migrations from new branches
echo "==> Applying pending D1 migrations (local)"
pnpm --filter api exec wrangler d1 migrations apply DB --local 2>/dev/null || true

echo "==> Container started. Local state in .wrangler/state/v3/"
```

## wrangler.toml Local Binding Configuration

The `wrangler.toml` references local persistence paths relative to the workspace, so the container's volume mount works correctly:

```toml
name = "api"
main = "src/index.ts"
compatibility_date = "2025-08-01"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "api-dev"
database_id = "00000000-0000-0000-0000-000000000000"
# Local-only: wrangler stores state in .wrangler/state/v3/d1/
# The volume mount keeps this across container rebuilds

[[kv_namespaces]]
binding = "CACHE"
id = "00000000000000000000000000000001"
preview_id = "00000000000000000000000000000001"

[[r2_buckets]]
binding = "ASSETS"
bucket_name = "api-assets-dev"

[dev]
port = 8787
local_protocol = "http"
ip = "0.0.0.0"
# 0.0.0.0 required for VS Code port forwarding to reach the container
```

## Anti-patterns

- Using `"localhost"` as the `ip` in `[dev]` — port forwarding in Codespaces only works when `wrangler dev` listens on `0.0.0.0`
- Mounting the entire `.wrangler` directory as a bind mount to the host — this breaks on Windows (SQLite file locking) and causes permission issues with Colima/Lima; named volumes are safer
- Running `wrangler d1 migrations apply` without `--local` in the post-create script — this hits the production D1 instance, which needs a real API token and modifies live data
- Installing Wrangler globally with `npm install -g wrangler` in the Dockerfile — prefer the pnpm workspace version so all developers use the same pinned version
- Omitting the `CLOUDFLARE_API_TOKEN` pass-through in `remoteEnv` — some `wrangler` subcommands require it even for local dev; the `${localEnv:...}` syntax safely forwards it without hardcoding

## Gotchas

- The `workers-local-persistence` named volume persists D1/R2/KV state across rebuilds but is machine-local; each developer has their own volume, not shared state
- `docker-in-docker` feature is needed if running Jaeger for OTEL local traces alongside `wrangler dev` — omit it if the project does not use Docker Compose in dev
- Codespaces caps the port forwarding to specific port numbers; if the project uses ports outside 8787–8797, add them explicitly to `forwardPorts`
- OrbStack on macOS does not always pick up `.devcontainer.json` changes without a full rebuild (`Dev Containers: Rebuild Container`); `postCreateCommand` changes especially need a rebuild
- `COREPACK_ENABLE_AUTO_PIN=0` prevents Corepack from modifying `package.json` when the container activates a different pnpm version than what the project pins

## Verification

```bash
# Inside the container: confirm wrangler version
wrangler --version

# Confirm local D1 is accessible
wrangler d1 execute DB --local --command "SELECT name FROM sqlite_master WHERE type='table'"

# Confirm KV local state
wrangler kv key get --binding=CACHE "health-check" --local

# Confirm R2 local state
wrangler r2 object get ASSETS/.devcontainer-ready --local --file /tmp/check.txt
cat /tmp/check.txt

# Start dev server and confirm port forwarding
wrangler dev --local &
sleep 3
curl -s http://localhost:8787/health | jq .
```

## Related

- `devcontainer-json.md` — general devcontainer patterns
- `wrangler-dev-local-d1-r2-kv.md` — local D1/R2/KV binding details
- `vscode-debugging-config.md` — VS Code launch.json for Workers debugging
- `cloudflare-workers-otel-local-trace-exporter.md` — adding Jaeger to the local stack

## Sources

- https://containers.dev/implementors/json_reference/
- https://developers.cloudflare.com/workers/wrangler/configuration/
- https://code.visualstudio.com/docs/devcontainers/containers
