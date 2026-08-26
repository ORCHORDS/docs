# Dev Containers and GitHub Codespaces

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

New engineers spend 1-2 days setting up their development environment.
"Works on my machine" bugs waste hours in code review. CI failures caused
by environment differences (Node version, system library, database
version) are common. Remote and cross-platform developers (macOS, Linux,
Windows) hit platform-specific issues.

## Context

Dev Containers define the entire development environment as code — OS,
runtime, tools, extensions, and services — in a `devcontainer.json` file.
Every developer and CI runs an identical, reproducible setup. They work
locally in VS Code (Dev Containers extension), in JetBrains IDEs (remote
development), and in the cloud via GitHub Codespaces. The Dev Container
spec is an open standard maintained by the Development Containers
community with support from Microsoft, GitHub, and JetBrains.

## devcontainer.json anatomy

```jsonc
// .devcontainer/devcontainer.json
{
  "name": "Project Dev Container",
  "image": "mcr.microsoft.com/devcontainers/typescript-node:22",

  // Features — composable, reusable environment modules
  "features": {
    "ghcr.io/devcontainers/features/docker-in-docker:2": {},
    "ghcr.io/devcontainers/features/github-cli:1": {},
    "ghcr.io/devcontainers/features/node:1": { "version": "22" }
  },

  // Forward ports from the container
  "forwardPorts": [3000, 5432],

  // Lifecycle hooks
  "postCreateCommand": "pnpm install",
  "postStartCommand": "pnpm dev &",

  // VS Code customization
  "customizations": {
    "vscode": {
      "extensions": [
        "dbaeumer.vscode-eslint",
        "esbenp.prettier-vscode",
        "bradlc.vscode-tailwindcss"
      ],
      "settings": {
        "editor.defaultFormatter": "esbenp.prettier-vscode",
        "editor.formatOnSave": true
      }
    }
  },

  // Environment variables
  "containerEnv": {
    "DATABASE_URL": "postgresql://dev:dev@db:5432/app"
  }
}
```

## Multi-container setup with Docker Compose

```jsonc
// .devcontainer/devcontainer.json
{
  "name": "Full Stack",
  "dockerComposeFile": "docker-compose.yml",
  "service": "app",
  "workspaceFolder": "/workspace",
  "forwardPorts": [3000, 5432, 6379]
}
```

```yaml
# .devcontainer/docker-compose.yml
services:
  app:
    build:
      context: ..
      dockerfile: .devcontainer/Dockerfile
    volumes:
      - ..:/workspace:cached
    command: sleep infinity

  db:
    image: postgres:17
    environment:
      POSTGRES_USER: dev
      POSTGRES_PASSWORD: dev
      POSTGRES_DB: app
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine

volumes:
  pgdata:
```

## Dev Container Features

Features are self-contained, composable units of installation code and
configuration. They replace manual Dockerfile customization for common
tools.

```jsonc
"features": {
  "ghcr.io/devcontainers/features/docker-in-docker:2": {},
  "ghcr.io/devcontainers/features/aws-cli:1": {},
  "ghcr.io/devcontainers/features/terraform:1": { "version": "1.9" },
  "ghcr.io/devcontainers/features/python:1": { "version": "3.12" }
}
```

## GitHub Codespaces

Cloud-hosted dev containers that launch in seconds from any repository.

### Configuration

```jsonc
// .devcontainer/devcontainer.json — Codespaces additions
{
  "hostRequirements": {
    "cpus": 4,
    "memory": "8gb",
    "storage": "32gb"
  },
  // Prebuilt images for faster startup
  "image": "ghcr.io/myorg/devcontainer:latest"
}
```

### Prebuilds

Codespaces prebuilds run `devcontainer.json` lifecycle commands ahead of
time and cache the result. New codespaces start in seconds instead of
minutes.

```yaml
# .github/workflows/codespaces-prebuild.yml
# Configured in repo Settings → Codespaces → Prebuilds
```

## Anti-patterns

- **Mega-container** — installing every tool in a single massive container
  image. Use Features to compose tools and keep the base image minimal.
- **No lifecycle hooks** — requiring manual setup steps after container
  creation defeats the purpose. Use `postCreateCommand` for one-time
  setup and `postStartCommand` for recurring tasks.
- **Ignoring dotfiles** — dev containers should respect personal dotfiles
  (shell config, Git config). Codespaces supports a dotfiles repository.
- **No GPU/resource specification** — ML workloads need GPU access and
  sufficient memory. Use `hostRequirements` to specify.

## Gotchas

- **Volume mounts on macOS** — file system performance on macOS Docker
  can be slow with large node_modules. Use `:cached` mount option and
  consider moving node_modules to a named volume.
- **Port conflicts** — forwarded ports conflict if the same port is used
  on the host. Dev containers handle this automatically, but manual
  Docker setups may not.
- **Secrets management** — do not hardcode secrets in devcontainer.json.
  Use Codespaces secrets (Settings → Codespaces → Secrets) or environment
  variable files excluded from Git.
- **Cold start time** — initial container builds can take minutes. Use
  prebuilt images and Codespaces prebuilds to reduce startup time.

## Verification

- `.devcontainer/devcontainer.json` exists in the repository root.
- New engineers can start developing within 10 minutes of cloning.
- CI and dev containers use the same base image and tool versions.
- No "works on my machine" bugs in the last quarter.
- Lifecycle hooks handle all setup — no manual steps documented in README.

## Related

- `documentation/docs/policies/infra/docker-best-practices.md`
- `documentation/docs/policies/github/codespaces-configuration.md`
- `documentation/docs/policies/devtools/ide-configuration.md`

## Source URLs (verified 2026-08-16)

- Dev Container spec — https://containers.dev/
- VS Code Dev Containers — https://code.visualstudio.com/docs/devcontainers/containers
- GitHub Codespaces — https://docs.github.com/en/codespaces/setting-up-your-project-for-codespaces/adding-a-dev-container-configuration/introduction-to-dev-containers
- Dev Containers in 2026 — https://viprasol.com/blog/devcontainers/
