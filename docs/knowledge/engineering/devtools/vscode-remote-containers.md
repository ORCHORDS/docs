# vscode-remote-containers

**Issue:** Works-on-my-machine environment differences between developers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
New team members spend days setting up local environment. OS differences cause subtle bugs.

## Pattern / Solution
Add .devcontainer/devcontainer.json pointing to a Dockerfile or image. Specify postCreateCommand for setup, forwardPorts for services, extensions for auto-install. Reopen in Container from command palette.

## Gotchas
- Volume mounts on Windows/WSL2 can have significant I/O performance issues for node_modules
- Use named volumes for node_modules to avoid re-install on rebuild

## Related
- devcontainer-json, docker-compose-dev, docker-desktop-setup
