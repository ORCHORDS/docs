# GitHub Actions — Self-Hosted Runners

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

GitHub-hosted runner minutes are exhausted before month-end, or
jobs queue for more than 10 minutes because no runner is idle.
Alternatively, a job fails with "No runner is available" when it
requests a custom label such as `self-hosted, linux, example project`.

## Context

example project runs compute-heavy jobs (D1 schema diffing, Playwright
E2E suites, Wrangler bundle analysis) that regularly exceed the
2 GB RAM ceiling of the free GitHub-hosted `ubuntu-latest` runner.
The platform team operates an ARC (Actions Runner Controller)
cluster on a managed Kubernetes service to provide ephemeral,
auto-scaled runners with up to 8 GB RAM per pod.

## 1. ARC Installation on Kubernetes

ARC manages GitHub Actions runners as Kubernetes pods using the
`actions-runner-controller` Helm chart. Install the controller
and a `RunnerDeployment` (or the newer `AutoscalingRunnerSet`)
in a dedicated namespace.

```bash
helm repo add actions-runner-controller \
  https://actions-runner-controller.github.io/actions-runner-controller

helm upgrade --install arc \
  actions-runner-controller/actions-runner-controller \
  --namespace arc-system \
  --create-namespace \
  --set authSecret.create=true \
  --set authSecret.github_token="$(cat github-pat.txt)"
```

Create an `AutoscalingRunnerSet` resource to define the runner
pool. Each runner pod is ephemeral — it registers, picks up one
job, and is destroyed.

```yaml
# arc-runnerscaleset.yaml
apiVersion: actions.github.com/v1alpha1
kind: AutoscalingRunnerSet
metadata:
  name: example project-runners
  namespace: arc-system
spec:
  githubConfigUrl: https://github.com/acme/example project
  githubConfigSecret: arc-controller-manager-github-auth
  minRunners: 2
  maxRunners: 20
  template:
    spec:
      containers:
        - name: runner
          image: ghcr.io/actions/actions-runner:latest
          resources:
            requests:
              cpu: "2"
              memory: "4Gi"
            limits:
              cpu: "4"
              memory: "8Gi"
```

## 2. Ephemeral Runners and Auto-scaling

Ephemeral runners (`--ephemeral` flag or ARC default) register
once, execute a single job, then deregister automatically. This
prevents secret leakage between jobs and simplifies cleanup.

```
Job queue depth → scale-up signal
│
├─ 0 pending jobs  → minRunners (2) idle pods kept warm
├─ 5 pending jobs  → scale to 5 pods
└─ 20 pending jobs → clamp at maxRunners (20)
```

ARC polls the GitHub Actions API every 30 seconds by default.
Reduce `scaleUpCoolDownSeconds` to 15 for faster burst response
during release windows:

```yaml
spec:
  scaleUpCoolDownSeconds: 15
  scaleDownDelaySecondsAfterScaleOut: 120
```

## 3. Runner Labels for Job Targeting

Labels declared in the `RunnerDeployment` spec are automatically
registered with GitHub. Use structured labels to route jobs to
the correct pool without ambiguity.

```yaml
# In AutoscalingRunnerSet spec
template:
  spec:
    containers:
      - name: runner
        env:
          - name: RUNNER_LABELS
            value: "self-hosted,linux,example project,8gb"
```

Reference the labels in workflow YAML:

```yaml
jobs:
  e2e:
    runs-on: [self-hosted, linux, example project, 8gb]
    steps:
      - uses: actions/checkout@v4
      - run: pnpm test:e2e
```

Using overly broad labels such as `self-hosted` alone risks
a job landing on a shared runner from a different team's pool.

## 4. Security Isolation

Ephemeral pods share no state between runs. However, the Docker
socket is a common attack surface when jobs build container images.

| Risk                      | Mitigation                             |
|---------------------------|----------------------------------------|
| Docker socket privilege   | Use rootless Podman or Kaniko          |
| npm/pnpm cache poisoning  | Mount a read-only cache volume         |
| Secrets in environment    | Use OIDC; avoid long-lived PATs        |
| Pod-to-pod network        | NetworkPolicy: deny all cross-pod      |
| Image pull from untrusted | Mirror images to internal registry     |

Apply a Kubernetes `NetworkPolicy` that limits egress to the
GitHub API and your internal Cloudflare endpoints only:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: arc-runner-egress
  namespace: arc-system
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: example project-runners
  policyTypes: [Egress]
  egress:
    - ports:
        - port: 443
```

## 5. OIDC Authentication vs PAT

Prefer OIDC tokens for registering runners rather than a
long-lived Personal Access Token. OIDC tokens are short-lived
and scoped to the installation.

```
PAT approach (avoid):
  GitHub PAT (no expiry) → stored in K8s Secret → ARC uses it
  Risk: PAT leaked from K8s Secret grants repo-wide write access

OIDC / GitHub App approach (preferred):
  GitHub App installation token (1 h TTL) → ARC refreshes
  Risk surface: limited to the token's TTL
```

Create a GitHub App with the `self_hosted_runners:write`
permission, install it on the target org, and supply
`APP_ID` + `PRIVATE_KEY` to the ARC Helm values instead of a PAT:

```yaml
# values.yaml for arc helm chart
authSecret:
  create: true
  github_app_id: "12345"
  github_app_installation_id: "67890"
  github_app_private_key: |
<redacted-private-key>
```

## 6. Cost Comparison vs GitHub-Hosted Runners

```
Workload: 200 Playwright E2E runs/month, 12 min each, 4-vCPU need

GitHub-hosted (ubuntu-latest-4-cores):
  200 × 12 min × $0.016/min = $38.40/month

Self-hosted on managed K8s (e2-standard-4 equivalent):
  Reserved node: ~$45/month (covers 20 concurrent runners)
  Amortised per run at 200/month: ~$0.225/run → $45/month base
  Benefit: no per-minute billing; burst to 20× at same node cost
```

For fewer than ~150 heavy runs per month, GitHub-hosted runners
are cheaper. Cross the threshold and the ARC cluster pays off
within two to three months of operation overhead.

## Anti-patterns

- Mounting the host Docker socket (`/var/run/docker.sock`) into
  runner pods; a compromised job gains root on the node.
- Using persistent (non-ephemeral) runners — leftover build
  artifacts and cached credentials from one job contaminate the
  next.
- Registering runners with only the `self-hosted` label in a
  multi-team org; any team's workflow can claim the runner.
- Storing the GitHub PAT as a plain Kubernetes Secret without
  encryption at rest; enable KMS envelope encryption.

## Gotchas

- ARC v0.x and the newer `AutoscalingRunnerSet` API (v1alpha1)
  are not compatible; check which CRD version your Helm chart
  installs before writing manifests.
- pnpm cache directories inside an ephemeral pod are lost between
  runs unless you mount a shared PVC or use a remote cache server.
- The `--ephemeral` flag requires ARC >= 0.23.0; older versions
  silently ignore it and leave runners in a reusable state.
- GitHub rate-limits the runner registration API; if you scale
  to more than 100 pods simultaneously you may hit 429 errors
  during burst registration.

## Verification

```bash
# List registered runners for the repo
gh api /repos/acme/example project/actions/runners --jq '.runners[].name'

# Watch ARC pod lifecycle during a test run
kubectl get pods -n arc-system -w

# Confirm no runner pod survives after a job completes
kubectl get pods -n arc-system \
  -l app.kubernetes.io/name=example project-runners
```

## Related

- documentation/docs/policies/github/github-actions-cloudflare-deploy-workflow.md
- documentation/docs/policies/github/github-actions-reusable-workflow-patterns.md
- documentation/docs/policies/infra/kubernetes-arc-cluster-setup.md
- documentation/docs/policies/security/oidc-token-short-lived-credentials.md

## Source URLs (verified 2026-08-17)

- https://github.com/actions/actions-runner-controller
- https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners-with-actions-runner-controller/quickstart-for-actions-runner-controller
- https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions#hardening-for-self-hosted-runners
- https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect
