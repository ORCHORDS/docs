# rollback-runbook

**Issue:** Step-by-step runbook for rolling back a bad production deployment quickly and safely
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A deployment introduces a regression — elevated error rates, latency increase, or business-logic defect. The team needs a rehearsed, low-panic procedure to restore the last known good state within minutes.

## Pattern / Solution
**Decision gate — rollback or hotfix?**
- Rollback if: symptom appeared within the last deploy window, no data-destructive migration ran
- Hotfix if: a forward-only migration already ran (rolling back would break schema)

**Kubernetes rollback (most common path)**
```bash
# See revision history
kubectl rollout history deployment/<name> -n <namespace>

# Roll back to previous revision
kubectl rollout undo deployment/<name> -n <namespace>

# Roll back to a specific revision
kubectl rollout undo deployment/<name> --to-revision=3 -n <namespace>

# Watch rollout progress
kubectl rollout status deployment/<name> -n <namespace>
```

**ECS / Fargate rollback**
```bash
# Re-deploy the previous task definition revision
aws ecs update-service \
  --cluster prod \
  --service api \
  --task-definition api:<previous-revision> \
  --force-new-deployment
```

**Cloudflare Workers / static assets**
```bash
# Roll back to a previous deployment via Wrangler
wrangler deployments list
wrangler rollback <deployment-id>
```

**After rollback**
1. Confirm error rate returns to baseline (≤ 5 min)
2. Write a timeline in the incident channel
3. Open a post-mortem ticket before declaring the incident closed
4. Protect the reverted revision from being overwritten until root cause is found

## Gotchas
- `kubectl rollout undo` rolls back the Pod template but does NOT roll back ConfigMaps or Secrets that changed alongside it
- If a migration removed a column the old code reads, rollback will cause immediate DB errors — you must forward-fix instead
- Rollback does not auto-scale; verify HPA/replica count matches prod expectations after undo
- Wrangler rollback is instant globally but Workers KV data is not rolled back

## Related
- `hotfix-process.md`
- `zero-downtime-deployment-checklist.md`
- `incident-runbook-template.md`
- `database-migration-zero-downtime.md`
