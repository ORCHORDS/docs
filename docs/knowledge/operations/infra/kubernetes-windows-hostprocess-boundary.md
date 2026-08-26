# Kubernetes Windows HostProcess boundary

**Problem**

Windows HostProcess containers run with host access and are not ordinary workload isolation.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use only for node-management agents that cannot operate through normal Windows containers.

## Controls

- Restrict to dedicated namespaces, service accounts, nodes, images, and admission policy.
- Run as the least host identity and pin image digests.
- Exclude untrusted repositories and PR code.

## Implementation

- Set HostProcess fields explicitly and validate compatible usernames.
- Separate rollout from application workloads.
- Audit host mutations.

## Tests

- Attempt filesystem, registry, service, network, and credential access; test cleanup and node reboot.

## Gotchas

- HostProcess can alter the node.
- Linux container security controls do not map directly.
- Failure cleanup may require host recovery.

## Official sources

- [Official documentation](https://kubernetes.io/docs/tasks/configure-pod-container/create-hostprocess-pod/)
