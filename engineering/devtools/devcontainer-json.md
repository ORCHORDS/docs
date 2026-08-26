# devcontainer-json

**Issue:** Dev container configuration not standardized across team
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Each developer has different container setup; devcontainer.json exists but is incomplete.

## Pattern / Solution
Use Dev Container spec features for common tools: node, docker-in-docker. Specify postCreateCommand for project setup. Use customizations.vscode.extensions for automatic extension install. Reference in docker-compose.yml via dockerComposeFile.

## Gotchas
- runArgs for Docker options — document unusual flags
- Rebuild container after devcontainer.json changes with Rebuild Container command

## Related
- vscode-remote-containers, docker-compose-dev
