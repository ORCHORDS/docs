# Dev Containers — Reproducible Local Development Environments

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

New developers spend 1-2 days setting up their local environment —
installing the correct versions of Node.js, Python, PostgreSQL, Redis,
Docker, and project-specific tools. "Works on my machine" is a weekly
occurrence because developers run different OS versions, tool versions,
and system configurations. Your CONTRIBUTING.md has 40 steps and is
perpetually outdated. CI passes but local tests fail because the CI
environment does not match developer laptops.

## Context

Dev Containers (Development Containers) are Docker-based development
environments defined by a `devcontainer.json` specification. The
developer's IDE (VS Code, JetBrains 2025+, GitHub Codespaces, Claude
Code) runs inside or connected to a container that has all tools,
dependencies, and configurations pre-installed. In 2026, the Dev
Container spec is an open standard maintained by the Dev Containers
community (devcontainers.dev), supported by VS Code, GitHub Codespaces,
JetBrains IDEs, and DevPod. The key value proposition: clone the repo,
open in IDE, and start coding — zero manual setup.

## devcontainer.json

```jsonc
// .devcontainer/devcontainer.json
{
  "name": "My Project",
  "image": "mcr.microsoft.com/devcontainers/typescript-node:22",

  // Or use a Dockerfile
  // "build": {
  //   "dockerfile": "Dockerfile",
  //   "context": ".."
  // },

  // Or use Docker Compose
  // "dockerComposeFile": "docker-compose.yml",
  // "service": "app",
  // "workspaceFolder": "/workspace",

  "features": {
    "ghcr.io/devcontainers/features/docker-in-docker:2": {},
    "ghcr.io/devcontainers/features/github-cli:1": {},
    "ghcr.io/devcontainers/features/aws-cli:1": {}
  },

  "customizations": {
    "vscode": {
      "extensions": [
        "dbaeumer.vscode-eslint",
        "esbenp.prettier-vscode",
        "ms-playwright.playwright"
      ],
      "settings": {
        "editor.formatOnSave": true,
        "editor.defaultFormatter": "esbenp.prettier-vscode"
      }
    }
  },

  "forwardPorts": [3000, 5432, 6379],

  "postCreateCommand": "npm ci",
  "postStartCommand": "npm run db:migrate",

  "remoteUser": "node",

  "mounts": [
    "source=${localWorkspaceFolder}/.env,target=/workspace/.env,type=bind"
  ]
}
```

## With Docker Compose (services)

```yaml
# .devcontainer/docker-compose.yml
services:
  app:
    build:
      context: ..
      dockerfile: .devcontainer/Dockerfile
    volumes:
      - ..:/workspace:cached
      - node_modules:/workspace/node_modules
    command: sleep infinity
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: myapp_dev
      POSTGRES_USER: dev
      POSTGRES_PASSWORD: dev
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - 5432:5432

  redis:
    image: redis:7-alpine
    ports:
      - 6379:6379

volumes:
  node_modules:
  pgdata:
```

```jsonc
// .devcontainer/devcontainer.json
{
  "name": "Full Stack",
  "dockerComposeFile": "docker-compose.yml",
  "service": "app",
  "workspaceFolder": "/workspace",
  "forwardPorts": [3000, 5432, 6379],
  "postCreateCommand": "npm ci && npm run db:migrate && npm run db:seed"
}
```

## Dev Container Features

```jsonc
// Features are reusable, shareable units of dev container config
{
  "features": {
    // Languages and runtimes
    "ghcr.io/devcontainers/features/python:1": { "version": "3.12" },
    "ghcr.io/devcontainers/features/rust:1": {},
    "ghcr.io/devcontainers/features/go:1": { "version": "1.22" },

    // Tools
    "ghcr.io/devcontainers/features/terraform:1": {},
    "ghcr.io/devcontainers/features/kubectl-helm-minikube:1": {},
    "ghcr.io/devcontainers/features/docker-in-docker:2": {},

    // Custom features from any OCI registry
    "ghcr.io/myorg/devcontainer-features/internal-cli:1": {}
  }
}
```

## Lifecycle scripts

```jsonc
{
  // Runs once when container is created
  "postCreateCommand": "npm ci && npx playwright install",

  // Runs every time container starts
  "postStartCommand": "npm run db:migrate",

  // Runs after dev container is attached to IDE
  "postAttachCommand": "git fetch --all",

  // Multi-command (object form)
  "postCreateCommand": {
    "deps": "npm ci",
    "playwright": "npx playwright install",
    "db": "npm run db:migrate && npm run db:seed"
  }
}
```

## Platform support

```
VS Code:
  → Native support via Remote - Containers extension
  → Local Docker or remote SSH host
  → Full IntelliSense, debugging, terminal

GitHub Codespaces:
  → Cloud-hosted dev containers
  → Uses same devcontainer.json
  → Prebuilds for faster startup
  → 2/4/8/16/32-core machines available

JetBrains (2025+):
  → Gateway + Dev Containers plugin
  → IntelliJ, WebStorm, PyCharm, GoLand
  → Remote development via SSH or Docker

DevPod:
  → Open-source, self-hosted alternative to Codespaces
  → Same devcontainer.json spec
  → Runs on any cloud (AWS, GCP, Azure) or local Docker
  → No vendor lock-in
```

## Anti-patterns

- **Heavyweight base images** — using a 2GB base image with every
  tool pre-installed. Container build time and pull time increase
  significantly. Use slim base images and add only needed tools via
  Features.
- **No volume for node_modules** — mounting `node_modules` from the
  host into the container causes platform mismatches (native modules
  compiled for macOS vs. Linux). Use a named Docker volume for
  `node_modules` to keep it container-native.
- **Secrets in devcontainer.json** — committing API keys, database
  passwords, or tokens in the dev container configuration. Use
  environment variable references, `.env` files (gitignored), or
  secret management tools.
- **Skipping prebuilds** — every developer rebuilding the container
  from scratch on clone. Use GitHub Codespaces prebuilds or cache
  Docker layers to reduce setup time from minutes to seconds.

## Gotchas

- **File system performance on macOS** — Docker Desktop on macOS has
  slower file system performance than Linux due to the VM layer.
  Use `:cached` volume mounts and named volumes for `node_modules`
  to mitigate. Consider using VS Code's "Clone in Volume" option.
- **Docker-in-Docker vs. Docker-outside-Docker** — if your project
  needs to run Docker commands inside the dev container, choose
  between DinD (full Docker daemon inside container) and DooD
  (mount host's Docker socket). DooD shares the host's Docker but
  has security implications.
- **Port conflicts** — if the host already uses port 5432 (local
  PostgreSQL), forwarding container port 5432 fails. Use different
  host ports in `forwardPorts` or stop conflicting local services.
- **Git credentials** — the container needs access to your Git
  credentials for pushing. VS Code automatically forwards your SSH
  agent or credential helper, but other tools may require manual
  configuration.

## Verification

- `devcontainer.json` exists in the repository root (`.devcontainer/`).
- New developers can start coding within 5 minutes of cloning.
- All services (database, cache, queue) run as dev container services.
- IDE extensions and settings are configured in devcontainer.json.
- Lifecycle scripts install dependencies and run migrations.
- CI environment matches the dev container configuration.

## Related

- `documentation/docs/policies/devtools/developer-experience-dx-metrics.md`
- `documentation/docs/policies/infra/iac-testing-terratest-checkov.md`
- `documentation/docs/policies/worktree/git-worktree-monorepo-parallel-ai-agents.md`

## Source URLs (verified 2026-08-16)

- Dev Containers Specification — https://containers.dev/
- VS Code Dev Containers Tutorial — https://code.visualstudio.com/docs/devcontainers/containers
- Dev Containers Best Practices 2026 — https://dev.to/ajeetraina/mastering-dev-containers-for-streamlined-development-2025-34d6
- DevPod: Open Source Dev Environments — https://devpod.sh/
