# docker-desktop-setup

**Issue:** Docker Desktop performance issues and license requirements on team machines
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Docker Desktop is slow on macOS, requires commercial license for large orgs, or conflicts with WSL2.

## Pattern / Solution
Alternatives: Rancher Desktop (free, runs containerd/dockerd), OrbStack (macOS, fast), Colima (CLI, lightweight). For Docker Desktop: enable VirtioFS for file sharing, allocate appropriate CPU/memory in settings.

## Gotchas
- Docker Desktop 4.0+ requires paid subscription for companies over 250 employees
- OrbStack uses macOS Virtualization.framework — fast but macOS only

## Related
- docker-compose-dev, devcontainer-json, lazydocker-patterns
