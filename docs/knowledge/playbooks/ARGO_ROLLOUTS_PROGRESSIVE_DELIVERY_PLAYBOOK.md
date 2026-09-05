# Argo Rollouts Progressive Delivery Playbook

## Purpose

Define the operational procedure for using Argo Rollouts to perform a canary deployment with traffic shifting, automated analysis, and rollback.

## Audience

Platform engineers, SREs, and release engineers.

## Pre-conditions

- Argo Rollouts 1.5+ (per `ARGO_VERSION_GOVERNANCE.md`).
- The cluster has Argo Rollouts controller installed.
- The service is a `Rollout` resource (not `Deployment`).

## Procedure

### Step 1 — Author the Rollout

1. Define a `Rollout` resource:
   - `strategy.canary.steps`.
   - `trafficRouting.istio` or `trafficRouting.nginx`.
   - `analysis.templates`.
2. Pin the Rollout to the same image tag pattern as the Deployment it replaces.

### Step 2 — Validate

3. `kubectl argo rollouts get rollout <name> --watch`.
4. `kubectl argo rollouts lint <name>`.
5. Confirm the Rollout is valid.

### Step 3 — Deploy the canary

6. Update the image:
   - `kubectl argo rollouts set image <name> <container>=<new-image>`.
7. Confirm the canary starts.
8. Confirm traffic shifts per the strategy.

### Step 4 — Analyze

9. Confirm analysis templates run.
10. Confirm success rate / latency / error rate are within thresholds.
11. Promote or pause based on analysis.

### Step 5 — Promote

12. `kubectl argo rollouts promote <name>`.
13. Confirm the canary progresses to 100%.
14. Confirm the stable ReplicaSet scales up and the canary scales down.

### Step 6 — Verify

15. Confirm the new version is healthy.
16. Confirm smoke tests pass.
17. Confirm metrics are at baseline.

### Step 7 — Rollback if needed

18. `kubectl argo rollouts abort <name>`.
19. Confirm the Rollout reverts to the stable version.
20. File a postmortem per `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.

## Rollback

If the canary fails analysis:

1. `kubectl argo rollouts undo <name>`.
2. Confirm traffic returns to the previous version.
3. Investigate the regression.

## References

- `ARGO_VERSION_GOVERNANCE.md`
- Argo Rollouts: `https://argoproj.github.io/argo-rollouts/`
- Traffic routing: `https://argoproj.github.io/argo-rollouts/features/traffic-routing/`
