# arc-github-runners-k8s

**Issue:** Actions Runner Controller — K8s-based GitHub Actions
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your CI takes 30 min. GitHub-hosted runners are
expensive. You have a K8s cluster. You want fast
self-hosted CI. You wish you had ARC.

## Root cause
**Self-hosted runners scale poorly without
orchestration.** Use ARC.

**Source:** GitHub ARC + OneUptime 2026 + YoungJu 2026.

## The "ARC" concept

Actions Runner Controller:
- **Type:** K8s operator
- **Maintained by:** GitHub
- **Mode:** Runner Scale Sets (current)
- **Scaling:** Min/max runners
- **Communication:** Long polling GitHub API

The ARC is the orchestrator.

## The "3 runner options" pattern

For choice:
| Option | Setup | Autoscaling | Cost (1000h/mo) |
|---|---|---|---|
| GitHub-hosted | None | Auto | ~$480 (2-core) |
| Self-hosted (VM) | Medium | DIY | EC2 + ops |
| ARC (K8s) | High | Native | K8s + ops |

The choice is per volume.

## The "decision criteria" pattern

For choice:
- **< 500h/mo:** GitHub-hosted
- **500-2000h + no K8s:** Self-hosted VM
- **> 2000h + K8s:** ARC

The decision is per volume.

## The "Runner Scale Sets" pattern

For current mode:
- **API:** Long poll GitHub
- **Scale-up:** On job queue
- **JIT token:** For registration
- **Ephemeral:** Default
- **Legacy mode:** Webhook (deprecated)

The scale set is the new way.

## The "scale-up flow" pattern

For flow:
1. **Listener** long-polls GitHub
2. **Job arrives** → message received
3. **Capacity check** — scale up?
4. **ACK** → patch EphemeralRunnerSet
5. **Pod created** → JIT registered
6. **Job runs** → Pod deleted

The flow is real-time.

## The "ARC install" pattern

For install:
```bash
# Controller
helm install arc \
  --namespace arc-systems \
  --create-namespace \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller

# Scale set
helm install repo-runners \
  --namespace arc-runners \
  --create-namespace \
  --set githubConfigUrl="https://github.com/org/repo" \
  --set githubConfigSecret.github_token="$GITHUB_PAT" \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set
```

The install is Helm.

## The "GitHub App vs PAT" pattern

For auth:
- **GitHub App:** Recommended (org-level, scoped)
- **PAT:** Works but tied to user (departs → broken)
- **Permissions:** Minimum needed

The App is preferred.

## The "GitHub App" pattern

For app:
```bash
# Create secret
kubectl create secret generic github-app-secret \
  --namespace arc-runners \
  --from-literal=github_app_id=12345 \
  --from-literal=github_app_installation_id=67890 \
  --from-file=github_app_private_key=./key.pem

# Install with secret
helm install repo-runners \
  --namespace arc-runners \
  --set githubConfigUrl="https://github.com/org/repo" \
  --set githubConfigSecret=github-app-secret \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set
```

The app is scoped.

## The "scale set values" pattern

For values:
```yaml
# values.yaml
githubConfigUrl: 'https://github.com/my-org'
githubConfigSecret: github-app-secret

# Scaling
minRunners: 2
maxRunners: 30

# Container mode
containerMode:
  type: 'kubernetes'
  kubernetesModeWorkVolumeClaim:
    accessModes: ['ReadWriteOnce']
    storageClassName: 'gp3'
    resources:
      requests:
        storage: 50Gi

# Resources
template:
  spec:
    containers:
    - name: runner
      image: ghcr.io/actions/actions-runner:latest
      resources:
        requests:
          cpu: '2'
          memory: '4Gi'
        limits:
          cpu: '4'
          memory: '8Gi'

# Node selection
nodeSelector:
  workload-type: ci-runner
tolerations:
- key: 'ci-runner'
  operator: 'Equal'
  value: 'true'
  effect: 'NoSchedule'
```

The values are tuned.

## The "ephemeral mode" pattern

For ephemeral:
- **Default:** True (in ARC)
- **Per job:** Pod created + deleted
- **Security:** No state leaks
- **Reproducibility:** Clean each run

The ephemeral is mandatory.

## The "runner version" pattern

For version:
- **Required:** v2.329.0+ (since March 2026)
- **Older:** Blocked from registration
- **Update:** Image + helm upgrade

The version is current.

## The "custom image" pattern

For image:
```dockerfile
# Dockerfile.runner
FROM ghcr.io/actions/actions-runner:2.329.0
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      python3 \
      nodejs && \
    rm -rf /var/lib/apt/lists/*
USER runner
```

The image is hardened.

## The "cache strategy" pattern

For cache:
- **PVC:** Persistent across pods
- **S3:** Cross-cluster
- **Registry:** Docker layers
- **Tool cache:** RUNNER_TOOL_CACHE

The cache is required.

## The "PVC cache" pattern

For PVC:
```yaml
template:
  spec:
    containers:
    - name: runner
      volumeMounts:
      - name: cache-volume
        mountPath: /opt/cache
      env:
      - name: RUNNER_TOOL_CACHE
        value: /opt/cache/tool-cache
      - name: npm_config_cache
        value: /opt/cache/npm
    volumes:
    - name: cache-volume
      persistentVolumeClaim:
        claimName: runner-cache-pvc
```

The cache is per PVC.

## The "network policy" pattern

For security:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: arc-runner
spec:
  podSelector: {}
  policyTypes:
  - Egress
  egress:
  # Only allow GitHub + cloud
  - to:
    - namespaceSelector: {}
  - to:
    - ipBlock:
        cidr: 0.0.0.0/0
        except:
        - 169.254.0.0/16  # metadata
```

The network is locked.

## The "security hardening" pattern

For Day 0:
- [ ] NetworkPolicy (egress only)
- [ ] SHA pinning (not tags)
- [ ] No public repo (block)
- [ ] No Docker socket
- [ ] Non-root runner user
- [ ] OIDC for cloud auth
- [ ] Secret scanning
- [ ] Monthly audit

The security is day 0.

## The "cluster autoscaler + ARC" pattern

For K8s:
- **Cluster Autoscaler:** EC2/GCE pool
- **Karpenter:** AWS, faster
- **Pattern:** Pods pending → scale nodes
- **Config:** Min/max nodes

The autoscaler is paired.

## The "monitoring" pattern

For metrics:
- **Prometheus:** ARC metrics
- **Grafana:** Dashboard
- **Alerts:**
  - Pool 90% exhausted
  - Registration failure
  - Prolonged Pending
  - Version drift
- **Per org:** Runner Group

The monitoring is per runner.

## The "March 2026 control plane fee" pattern

For cost:
- **$0.002/min:** Control plane fee
- **Excludes:** Public repos + GHES
- **Impact:** ~$60-100/mo for 1k hr

The fee is per minute.

## The "debugging" pattern

For issues:
```bash
# Listener logs
kubectl logs -n arc-systems \
  -l app.kubernetes.io/component=runner-scale-set-listener

# GitHub auth check
kubectl exec -n arc-systems \
  deploy/arc-gha-runner-scale-set-controller -- \
  curl -s https://api.github.com/meta | jq '.actions[]'

# Runner registration
kubectl get ephemeralrunner -n arc-runners

# Runner labels
kubectl get autoscalingrunnersets -n arc-runners -o yaml
```

The debugging is per issue.

## The "v2.329.0 requirement" pattern

For version:
- **Cutoff:** March 16, 2026
- **Below:** Blocked
- **Update:** Helm upgrade + new image
- **CI:** Test before enforcement

The version is enforced.

## The "GitHub-hosted vs ARC cost" pattern

For cost:
- **GitHub-hosted:** $0.008/min (2-core Linux)
- **ARC + EC2:** EC2 cost + ops
- **Break-even:** ~500 hr/mo
- **Above:** ARC wins
- **Below:** GitHub-hosted wins

The break-even is per volume.

## The "internal network access" pattern

For VPN:
- **GitHub-hosted:** Not possible
- **Self-hosted/ARC:** Yes (in VPC)
- **Use:** Internal packages, private deps

The network is the win.

## The "GPU support" pattern

For GPU:
- **GitHub-hosted:** Limited
- **ARC:** NVIDIA Device Plugin
- **Use:** ML training, CUDA

The GPU is per need.

## The "ephemeral mandatory" pattern

For ephemeral:
- **Why:** Security + reproducibility
- **Default:** True in ARC
- **Per VM:** `./config.sh --ephemeral`

The ephemeral is required.

## The "no ARC" anti-pattern

For no ARC:
- **Issue:** Slow, expensive CI
- **Fix:** ARC on K8s

The ARC is for K8s.

## The "PAT for org" anti-pattern

For PAT:
- **Issue:** User-bound
- **Fix:** GitHub App

The app is scoped.

## The "no NetworkPolicy" anti-pattern

For no NP:
- **Issue:** Egress to anywhere
- **Fix:** NetworkPolicy

The NP is required.

## The "legacy mode" anti-pattern

For legacy:
- **Issue:** Webhook-based, slow scale
- **Fix:** Runner Scale Sets

The new mode is required.

## The "ARC checklist" pattern

For checklist:
- [ ] GitHub App auth (not PAT)
- [ ] Runner Scale Sets (not legacy)
- [ ] minRunners + maxRunners set
- [ ] Ephemeral mode on
- [ ] Runner v2.329.0+
- [ ] NetworkPolicy applied
- [ ] SHA pinned actions
- [ ] OIDC for cloud
- [ ] Cache (PVC or S3)
- [ ] Cluster Autoscaler paired
- [ ] Prometheus + Grafana
- [ ] Pool exhaustion alert

The checklist is 12.

## Verification
- **Test:** Pods scale up
- **Test:** Jobs run successfully
- **Test:** Pods scale down
- **Test:** Cache works
- **Test:** NetworkPolicy blocks
- **Audit:** Monthly

## Gotchas
- **The "PAT for org" anti-pattern.** Use App.
- **The "no NP" anti-pattern.** Lock egress.
- **The "legacy mode" anti-pattern.** Use Scale Sets.

## Related
- `infra/github-self-hosted-runners.md`
- `github/github-actions-reusable-workflows.md`
- `github/branch-protection-and-codeowners.md`
- `infra/iac-best-practices.md`
- ARC GitHub: https://github.com/actions/actions-runner-controller
- OneUptime: https://oneuptime.com/blog/post/2026-02-09-github-actions-self-hosted-runners-k8s/view
- YoungJu: https://www.youngju.dev/blog/devops/2026-03-05-devops-github-actions-self-hosted-runner-ops.en
