# github-codespaces-devcontainer

**Issue:** Configuring a dev container so Codespaces and local devcontainer users get a consistent environment
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without a devcontainer, each developer installs tools differently, causing "works on my machine" issues. Codespaces uses `.devcontainer/devcontainer.json` to provision a standardised environment.

## Pattern / Solution
`.devcontainer/devcontainer.json`:
```json
{
  "name": "My Project",
  "image": "mcr.microsoft.com/devcontainers/javascript-node:22",
  "features": {
    "ghcr.io/devcontainers/features/github-cli:1": {},
    "ghcr.io/devcontainers/features/docker-in-docker:2": {}
  },
  "postCreateCommand": "npm ci",
  "forwardPorts": [3000, 5432],
  "customizations": {
    "vscode": {
      "extensions": ["dbaeumer.vscode-eslint", "esbenp.prettier-vscode"]
    }
  },
  "secrets": {
    "MY_API_KEY": { "description": "API key for the service" }
  }
}
```

## Gotchas
- Base images from `mcr.microsoft.com/devcontainers/` include common tools and a non-root user.
- `postCreateCommand` runs after the container is created but before the user session starts.
- Secrets in `devcontainer.json` are Codespaces-specific and not available locally.
- Rebuilding the container after changing `devcontainer.json` is required to pick up changes.
- VS Code Dev Containers extension lets you use the same config locally without Codespaces.

## Related
- `github-actions-self-hosted-runners-2026.md`
- `github-advanced-security-setup.md`
