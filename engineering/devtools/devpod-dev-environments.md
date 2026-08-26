# devpod-dev-environments

**Issue:** Dev environments not reproducible across machines and cloud providers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Local devcontainers work but spinning up cloud dev environments is manual and provider-specific.

## Pattern / Solution
DevPod is an open-source Codespaces alternative. devpod up git-repo spins up dev environment locally or in cloud (AWS, GCP, Azure, Kubernetes). Uses devcontainer.json. devpod ssh connects to environment. Provider-agnostic configuration.

## Gotchas
- DevPod requires Docker or a cloud provider configured as backend
- Persistent workspaces: devpod list shows running environments; devpod stop name to pause

## Related
- devcontainer-json, vscode-remote-containers, docker-desktop-setup
