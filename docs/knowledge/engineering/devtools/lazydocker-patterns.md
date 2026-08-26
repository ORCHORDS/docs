# lazydocker-patterns

**Issue:** Managing Docker containers requires many docker ps/logs/exec commands
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Checking container status, tailing logs, and managing volumes requires multiple commands.

## Pattern / Solution
lazydocker TUI shows containers, images, volumes, networks. Tab to switch panels. [ and ] cycle through containers. d for docker-compose logs. Enter for container details. Works with standalone containers and compose stacks.

## Gotchas
- Requires Docker socket access — may need sudo or docker group membership
- Compose stack detection works from any directory in the stack

## Related
- docker-compose-dev, docker-desktop-setup, k9s-kubernetes-tui
