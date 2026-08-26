# Docker Compose UTS namespace sharing

**Problem**

Sharing a UTS namespace couples hostname/domainname state between containers and weakens isolation assumptions.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use only when applications explicitly require shared hostname identity.

## Controls

- Declare `uts` deliberately and avoid host UTS for untrusted services.
- Keep network/service discovery independent of hostname mutation.
- Restrict hostname-changing capability.

## Implementation

- Document the sharing topology.
- Prefer service DNS names.
- Validate runtime support.

## Tests

- Change hostname in one container and observe peers.
- Test scale, restart, and host mode denial.

## Gotchas

- UTS sharing is not network sharing.
- Hostname is not workload identity.
- Host mode increases impact.

## Official sources

- [Official documentation](https://docs.docker.com/reference/compose-file/services/#uts)
