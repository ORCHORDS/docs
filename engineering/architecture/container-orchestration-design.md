# container-orchestration-design

**Issue:** Running containers manually does not provide scheduling, health checks, or self-healing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A fleet of Docker containers requires manual intervention to restart crashed instances and rebalance load after node failures.

## Pattern / Solution
Use Kubernetes or a managed equivalent such as ECS or Cloud Run. Define desired state declaratively. The orchestrator handles scheduling, health checking, rolling updates, and scaling. Use namespaces and resource quotas for multi-team isolation.

## Gotchas
Kubernetes adds significant operational complexity. For small teams, managed services trade control for simplicity. Misconfigured resource limits cause noisy-neighbor problems on shared nodes.

## Related
service-discovery-patterns, configuration-management, canary-deployment-architecture
