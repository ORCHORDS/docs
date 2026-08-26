# Docker Compose interface-name stability boundaries

**Issue**

Applications that bind policy or metrics to eth0-style names can break when multi-network attachment order changes.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use Compose `interface_name` only where the runtime supports it.
- Keep application policy based on addresses or routes when possible.
- Require unique interface names within each service namespace.

## Verification

1. Reorder networks, recreate containers, and inspect links/routes.
2. Test upgrades and scale-out replicas.
3. Fail configuration on duplicate or invalid names.

## Gotchas

- Stable names do not guarantee stable addresses.
- Engine/platform support varies.
- Interface naming cannot override host network security.

## Official source

- [Official documentation](https://docs.docker.com/reference/compose-file/services/#interface_name)
